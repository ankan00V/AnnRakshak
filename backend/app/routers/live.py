"""Live field walk over a WebSocket.

Protocol (JSON messages):
  client -> {"type": "start", "lang": "mr", "mode": "walk"|"video", "lat": ..., "lon": ...}
  server -> {"type": "ready", "context": {...}, "guide": {...}, "photo_model": true}
  client -> {"type": "frame", "seq": 7, "data": "<base64 JPEG, <=400 KB>"}
  server -> {"type": "frame", "seq": 7, "quality": {...}, "counted": bool, "advanced": bool,
             "live": {"top": [...]} | null, "guide": {...}}
  server -> {"type": "ask", "cue_id", "question", "candidates"}      (at most once)
  client -> {"type": "answer", "cue_id": "...", "answer": "yes|no|unknown"}
  server -> {"type": "steps_done"}                                   (all views collected)
  client -> {"type": "end_of_video"}                                 (video: no more frames)
  client -> {"type": "finish", "send_to_expert": false}
  server -> {"type": "summary", "summary": {...}}  and closes.

A disconnect before "finish" saves nothing. Frames are decoded in memory and
dropped; only evidence frames for a finding are written, as problem photos.

Two sources feed the same machinery. A phone walks the field and is guided view
by view. A computer cannot be carried there, so it reads a video the farmer
filmed earlier: the frames arrive the same way, but nothing is asked for and
nothing is coached — the video is already shot. Either way a problem is reported
as seen only when two separate frames agree.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import secrets
import time
from dataclasses import dataclass

from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app import auth, config, live
from app.db import SessionLocal, get_db
from app.engine.livescan import decode
from app.kb import KB, get_kb, tr
from app.models import Farm, LiveScan

router = APIRouter(prefix="/api", tags=["live"], dependencies=[Depends(auth.require())])
MAX_FRAME_BYTES = 400_000
MAX_FRAMES = 600
MAX_SECONDS = 600
#: How long a connection may stay silent before it is treated as gone. The phone
#: sends a frame about twice a second while walking and a ping while it waits
#: for the farmer to answer a question, so silence this long means the phone is
#: asleep, flat or out of signal — not that somebody is thinking.
IDLE_SECONDS = 90
#: How long a caller has to say what they want after connecting.
OPENING_SECONDS = 15
#: The outside edge of a call. MAX_SECONDS stops new frames but still lets the
#: farmer finish and keep what they walked; this is the point where a socket is
#: let go whatever it claims to be doing, so a stream of pings cannot hold a
#: place in the queue for ever.
HARD_SECONDS = MAX_SECONDS + 180
from app.i18n import LANGS  # noqa: E402

T = TypeVar("T")


@contextmanager
def _db() -> Iterator[Session]:
    """A database session for one piece of work, and not a moment longer.

    A call lasts minutes. A pooled connection does not belong to anyone for
    minutes: the pool holds fifteen, and behind PgBouncer's transaction pooling
    an open transaction pins a server connection too. Keeping one for the length
    of a walk means fifteen farmers can stop the whole application, and an idle
    transaction that outlives the pooler's patience is cut from under the call
    anyway. So the database is opened for the opening checks, for the context,
    and for the save at the end — never across the frames, which need none of it.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


#: A call whose connection dropped, kept warm for a short while so the farmer
#: can pick it up where it fell over. A walk is five minutes in a field on a
#: patchy network: dropping it means they walk it again from the edge of the
#: field, which is the quickest way to make a flagship feature unusable.
#:
#: Each parked call holds its evidence frames — three per problem, three
#: close-ups — so a couple of megabytes at worst, and the number of them is
#: capped. They live in this worker's memory: with more than one worker a
#: reconnection may land elsewhere and find nothing, which is simply today's
#: behaviour, so nothing is lost by trying.
_parked: dict[str, "_Parked"] = {}
RESUME_SECONDS = 180
MAX_PARKED = 24


@dataclass
class _Parked:
    at: float
    farm_id: int
    user_id: int | None
    sess: object
    ctx: dict
    lang: str
    spent: float


def _sweep_parked(now: float) -> None:
    for tok in [t for t, p in _parked.items() if now - p.at > RESUME_SECONDS]:
        _parked.pop(tok, None)
    while len(_parked) > MAX_PARKED:
        _parked.pop(min(_parked, key=lambda t: _parked[t].at), None)


def _park(farm_id: int, user_id: int | None, sess, ctx: dict, lang: str, spent: float) -> str:
    now = time.monotonic()
    _sweep_parked(now)
    token = secrets.token_urlsafe(24)
    _parked[token] = _Parked(now, farm_id, user_id, sess, ctx, lang, spent)
    return token


def _unpark(token: str, farm_id: int, user_id: int | None) -> "_Parked | None":
    """Pick a dropped call back up. The token alone is not enough: it must be
    the same field and the same person, so a token that leaked is still useless
    to anybody else."""
    now = time.monotonic()
    _sweep_parked(now)
    p = _parked.get(token)
    if p is None or p.farm_id != farm_id or p.user_id != user_id or now - p.at > RESUME_SECONDS:
        return None
    return _parked.pop(token)


_calls: Counter[int | None] = Counter()


def _in_progress() -> int:
    return sum(_calls.values())


@contextmanager
def _one_more_call(user_id: int | None) -> Iterator[None]:
    """Count the calls in flight, and whose they are. A single worker's event
    loop runs them all, so a plain counter is the whole of it — nothing else
    runs between the read and the write.

    Counting by caller as well as in total matters: a cap that only counts the
    total is a cap one account can fill on its own."""
    _calls[user_id] += 1
    try:
        yield
    finally:
        _calls[user_id] -= 1
        if _calls[user_id] <= 0:
            del _calls[user_id]


async def _in_db(work: Callable[[Session], T]) -> T:
    """Run `work` on a short-lived session, off the event loop.

    These calls go to a database that may be a continent away. Awaiting them on
    the loop itself would stall every other request on the worker for as long as
    the round trip takes.
    """
    def run() -> T:
        with _db() as db:
            return work(db)
    return await run_in_threadpool(run)


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

    def may_open(db: Session) -> tuple[str | None, str, int | None]:
        """Whether this call may happen, the field's own language, and who is
        calling. Read, and then let the connection go: nothing below here needs
        the database."""
        farm = db.get(Farm, farm_id)
        if farm is None:
            return "FARM_NOT_FOUND", "en", None
        user = auth.ws_user(ws, db)
        if not auth.can_open_farm(user, farm, db):
            return "NOT_ALLOWED", "en", None
        # A live walk records a scan against the field it is pointed at, and
        # the shared demo fields are everybody's. Reading one is fine; walking
        # one with a camera writes to what the next visitor sees.
        if auth.is_shared_demo(farm):
            return "DEMO_READ_ONLY", "en", None
        return None, farm.lang, (user.id if user else None)

    refusal, farm_lang, user_id = await _in_db(may_open)
    if refusal:
        await ws.send_json({"type": "error", "code": refusal})
        await ws.close(code=1000 if refusal == "FARM_NOT_FOUND" else 1008)
        return

    # A socket that connects and then says nothing is not a call and is not
    # charged as one: counting it would let anyone hold every place in the
    # queue just by opening connections and going quiet.
    try:
        start = await asyncio.wait_for(ws.receive_json(), OPENING_SECONDS)
    except (TimeoutError, WebSocketDisconnect):
        with contextlib.suppress(Exception):
            await ws.close(code=1000)
        return
    opening = start.get("type")
    if opening not in ("start", "resume"):
        await ws.send_json({"type": "error", "code": "EXPECTED_START"})
        await ws.close()
        return

    # Every frame of every call runs the model on a worker thread. Past a point
    # more callers do not mean more throughput, only that each one waits longer
    # and all of them time out together. Turning the next caller away with a
    # reason they can act on beats degrading the calls already under way.
    if _in_progress() >= config.LIVE_MAX_CALLS or _calls[user_id] >= config.LIVE_MAX_PER_CALLER:
        await ws.send_json({"type": "error", "code": "TOO_BUSY"})
        await ws.close(code=1013)
        return

    # Set before the try, because a drop part-way through setting a call up
    # lands in the handler below with none of this assigned.
    sess, ctx, lang, resume_token, settled = None, {}, farm_lang, "", True

    with _one_more_call(user_id):
        try:

            if opening == "resume":
                picked = _unpark(str(start.get("token") or ""), farm_id, user_id)
                if picked is None:
                    # Too long ago, a different worker, or not theirs. Nothing is
                    # wrong with the connection: the client starts a fresh walk.
                    await ws.send_json({"type": "error", "code": "RESUME_UNKNOWN"})
                    await ws.close()
                    return
                sess, ctx, lang, spent = picked.sess, picked.ctx, picked.lang, picked.spent
            else:
                lang = start.get("lang") if start.get("lang") in LANGS else farm_lang
                mode = "video" if start.get("mode") == "video" else "walk"
                lat, lon = start.get("lat"), start.get("lon")
                if not (isinstance(lat, int | float) and isinstance(lon, int | float)):
                    lat = lon = None
                accuracy = start.get("accuracy")

                def begin(db: Session):
                    farm = db.get(Farm, farm_id)
                    return (live.context(db, kb, farm, lat, lon, accuracy, lang),
                            live.new_session(kb, farm, lang, mode))

                ctx, sess = await _in_db(begin)
                spent = 0.0

            # What a dropped connection would come back with. Spent on first
            # use, so every reconnection is handed a fresh one.
            resume_token = secrets.token_urlsafe(24)
            await ws.send_json({"type": "ready", "context": ctx, "guide": sess.guide(),
                                "photo_model": sess.can_classify, "resume": resume_token,
                                "resumed": opening == "resume"})
            # Time already spent carries across a reconnection, so a call cannot
            # be stretched past its limit by dropping and dialling back in.
            began, announced_done = time.monotonic() - spent, False
            settled = False  # finished, or refused: nothing left worth parking

            async def announce_done() -> None:
                """Everything that is going to be looked at has been. Ask the Doubt
                Doctor question if two problems are still competing, then hand over."""
                nonlocal announced_done
                if announced_done:
                    return
                cue = sess.pending_question(kb)
                if cue:
                    a, b = cue["pair"]
                    await ws.send_json({"type": "ask", "cue_id": cue["id"],
                                        "question": tr(cue["question"], lang),
                                        "candidates": [kb.target_view(a, lang), kb.target_view(b, lang)]})
                await ws.send_json({"type": "steps_done", "asked": bool(cue)})
                announced_done = True

            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive_json(), IDLE_SECONDS)
                except TimeoutError:
                    break   # gone quiet: hold the walk, hand the place back
                # Past this point a call is let go whatever it is sending. The
                # frame limit below still lets a farmer at MAX_SECONDS finish
                # and keep what they walked; this is the outside edge.
                if time.monotonic() - began > HARD_SECONDS:
                    break
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
                    if sess.done:
                        await announce_done()
                elif kind == "end_of_video" and sess.mode == "video":
                    # The file ran out. However much of it was worth reading is what
                    # the summary is built from — a thin reading goes to an expert.
                    sess.ended = True
                    await announce_done()
                elif kind == "skip":
                    # The farmer cannot get this view. Moving on beats coaching
                    # towards a picture that does not exist until the clock runs
                    # out; the evidence rules already handle a thinner walk.
                    if sess.skip():
                        await ws.send_json({"type": "guide", "guide": sess.guide(), "advanced": True})
                        if sess.done:
                            await announce_done()
                elif kind == "answer":
                    sess.on_answer(str(msg.get("cue_id")), str(msg.get("answer")))
                    await ws.send_json({"type": "answered"})
                elif kind == "finish":
                    to_expert = bool(msg.get("send_to_expert"))

                    def save(db: Session):
                        farm = db.get(Farm, farm_id)
                        # Minutes have passed. The session that opened this call may
                        # have been signed out, revoked or expired since; a walk that
                        # is nobody's any more is not written to anybody's field.
                        if farm is None or not auth.can_open_farm(auth.ws_user(ws, db), farm, db):
                            return None
                        return live.finish(db, kb, farm, sess, ctx, lang, to_expert)

                    summary = await _in_db(save)
                    settled = True
                    if summary is None:
                        await ws.send_json({"type": "error", "code": "NOT_ALLOWED"})
                        await ws.close(code=1008)
                        return
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
            pass  # nothing was written, so there is nothing to undo

        # Dropped, gone quiet, or simply out of time. Either way the walk itself
        # is worth something: a farmer halfway down a field on a patchy network
        # should not have to start again at the gate, so the session waits a few
        # minutes for them to dial back in.
        if not settled and sess is not None and sess.mode == "walk" and sess.good_frames:
            now = time.monotonic()
            _parked[resume_token] = _Parked(now, farm_id, user_id, sess, ctx, lang, now - began)
            _sweep_parked(now)
        with contextlib.suppress(Exception):
            await ws.close(code=1001)
