"""Live field walk over a WebSocket.

Protocol (JSON messages):
  client -> {"type": "start", "lang": "mr", "lat": 21.1, "lon": 79.6, "accuracy": 12}
  server -> {"type": "ready", "context": {...}, "guide": {...}, "photo_model": true}
  client -> {"type": "frame", "seq": 7, "data": "<base64 JPEG, <=400 KB>"}
  server -> {"type": "frame", "seq": 7, "quality": {...}, "counted": bool, "advanced": bool,
             "live": {"top": [...]} | null, "guide": {...}}
  server -> {"type": "ask", "cue_id", "question", "candidates"}      (at most once)
  client -> {"type": "answer", "cue_id": "...", "answer": "yes|no|unknown"}
  server -> {"type": "steps_done"}                                   (all views collected)
  client -> {"type": "finish", "send_to_expert": false}
  server -> {"type": "summary", "summary": {...}}  and closes.

A disconnect before "finish" saves nothing. Frames are decoded in memory and
dropped; only evidence frames for a finding are written, as problem photos.
"""

from __future__ import annotations

import base64
import binascii
import time

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app import auth, live
from app.db import SessionLocal, get_db
from app.engine.livescan import decode
from app.kb import KB, get_kb, tr
from app.models import Farm, LiveScan

router = APIRouter(prefix="/api", tags=["live"], dependencies=[Depends(auth.require())])
MAX_FRAME_BYTES = 400_000
MAX_FRAMES = 600
MAX_SECONDS = 600
from app.i18n import LANGS  # noqa: E402


@router.get("/farms/{farm_id}/live/context")
def live_context(farm_id: int, lat: float | None = None, lon: float | None = None, accuracy: float | None = None,
                 lang: str = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = db.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")
    return live.context(db, kb, farm, lat, lon, accuracy, lang if lang in LANGS else "en")


@router.get("/farms/{farm_id}/live/{scan_id}")
def live_summary(farm_id: int, scan_id: int, lang: str = "en", db: Session = Depends(get_db),
                 kb: KB = Depends(get_kb)):
    """A finished walk's summary in `lang` — for a language switch on the summary screen."""
    scan = db.get(LiveScan, scan_id)
    if scan is None or scan.farm_id != farm_id:
        raise HTTPException(404, "live check not found")
    return live.render(db, kb, db.get(Farm, farm_id), scan, lang if lang in LANGS else "en")


@router.websocket("/live/{farm_id}")
async def live_ws(ws: WebSocket, farm_id: int):
    await ws.accept()
    kb = get_kb()
    db = SessionLocal()
    try:
        farm = db.get(Farm, farm_id)
        if farm is None:
            await ws.send_json({"type": "error", "code": "FARM_NOT_FOUND"})
            await ws.close()
            return
        if not auth.can_open_farm(auth.ws_user(ws, db), farm):
            await ws.send_json({"type": "error", "code": "NOT_ALLOWED"})
            await ws.close(code=1008)
            return
        start = await ws.receive_json()
        if start.get("type") != "start":
            await ws.send_json({"type": "error", "code": "EXPECTED_START"})
            await ws.close()
            return
        lang = start.get("lang") if start.get("lang") in LANGS else farm.lang
        lat, lon = start.get("lat"), start.get("lon")
        if not (isinstance(lat, int | float) and isinstance(lon, int | float)):
            lat = lon = None
        ctx = await run_in_threadpool(live.context, db, kb, farm, lat, lon, start.get("accuracy"), lang)
        sess = live.new_session(kb, farm, lang)
        await ws.send_json({"type": "ready", "context": ctx, "guide": sess.guide(), "photo_model": sess.can_classify})
        began, announced_done = time.monotonic(), False

        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "frame":
                if sess.frames >= MAX_FRAMES or time.monotonic() - began > MAX_SECONDS:
                    await ws.send_json({"type": "error", "code": "SESSION_LIMIT"})
                    continue
                try:
                    jpeg = base64.b64decode(msg.get("data") or "", validate=True)
                except (binascii.Error, ValueError):
                    await ws.send_json({"type": "error", "code": "BAD_FRAME", "seq": msg.get("seq")})
                    continue
                if not jpeg or len(jpeg) > MAX_FRAME_BYTES:
                    await ws.send_json({"type": "error", "code": "FRAME_SIZE", "seq": msg.get("seq")})
                    continue
                try:
                    img = await run_in_threadpool(decode, jpeg)
                except Exception:  # noqa: BLE001  unreadable frame: skip it, keep the call going
                    await ws.send_json({"type": "error", "code": "BAD_FRAME", "seq": msg.get("seq")})
                    continue
                out = await run_in_threadpool(sess.on_frame, img, jpeg,
                                              live.classify if sess.can_classify else None)
                await ws.send_json({"type": "frame", "seq": msg.get("seq")} | out)
                if sess.done and not announced_done:
                    cue = sess.pending_question(kb)
                    if cue:
                        a, b = cue["pair"]
                        await ws.send_json({"type": "ask", "cue_id": cue["id"],
                                            "question": tr(cue["question"], lang),
                                            "candidates": [kb.target_view(a, lang), kb.target_view(b, lang)]})
                    await ws.send_json({"type": "steps_done", "asked": bool(cue)})
                    announced_done = True
            elif kind == "answer":
                sess.on_answer(str(msg.get("cue_id")), str(msg.get("answer")))
                await ws.send_json({"type": "answered"})
            elif kind == "finish":
                summary = await run_in_threadpool(live.finish, db, kb, farm, sess, ctx, lang,
                                                  bool(msg.get("send_to_expert")))
                await ws.send_json({"type": "summary", "summary": summary})
                await ws.close()
                return
            elif kind == "lang" and msg.get("lang") in LANGS:  # switched language mid-call
                lang = msg["lang"]
                live.relang(kb, sess, lang)
                ctx = live.localize_context(kb, ctx, lang)
                await ws.send_json({"type": "lang", "lang": lang, "context": ctx, "guide": sess.guide()})
            elif kind == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        db.rollback()  # walked away before finishing: nothing is saved
    finally:
        db.close()
