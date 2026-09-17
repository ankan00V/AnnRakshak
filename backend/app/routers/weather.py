"""Weather for the farmer, and every way a notice reaches them.

  GET  /api/farms/{id}/weather                 the weather screen (all parameters, advice, spray window, water)
  GET  /api/farms/{id}/notices                 notification inbox;  POST .../notices/read
  GET  /api/farms/{id}/events                  Server-Sent Events: new notices/alerts while the app is open
  GET  /api/push/key                           VAPID public key for the browser
  POST /api/farms/{id}/push/subscribe          register this phone;  POST /api/push/unsubscribe
  POST /api/farms/{id}/push/test               a test notification to this farm's phones
  POST /api/farms/{id}/sprays                  "I'm spraying now" -> is it a good time, and watch for rain after
  GET|PUT /api/farms/{id}/contact              email address and which emails
  POST /api/farms/{id}/email/test|summary      a test email / today's summary now
  GET|POST /api/email/unsubscribe?token=       one-click unsubscribe (link and List-Unsubscribe-Post)
  POST /api/officials/watch/run                one watcher sweep now (demo, ops)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import auth, live, notify, services, watch
from app.config import EMAIL_BACKEND
from app.db import get_db
from app.engine import agromet, agroweather, satellite
from app.kb import KB, get_kb, tr
from app.limits import limit as rate_limit
from app.mailer import valid_address
from app.models import Farm, Notice, PushSubscription, SprayLog

router = APIRouter(prefix="/api", tags=["weather"], dependencies=[Depends(auth.require())])

EMAIL_PREFS = ("warnings", "all", "digest", "off")
SSE_MAX_SECONDS = 300
PUSH_TEST_TITLE = {"en": "AnnRakshak notifications are on", "hi": "AnnRakshak सूचनाएँ चालू हैं",
                   "mr": "AnnRakshak सूचना सुरू आहेत"}
PUSH_TEST_BODY = {"en": "Weather warnings for your {crop} will reach this phone.",
                  "hi": "आपकी {crop} के लिए मौसम चेतावनी इस फ़ोन पर आएगी।",
                  "mr": "तुमच्या {crop} साठी हवामान इशारे या फोनवर येतील."}


def _farm(db: Session, farm_id: int) -> Farm:
    farm = db.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")
    return farm


def _bundle(farm: Farm) -> dict:
    try:
        return agroweather.bundle(farm.lat, farm.lon)
    except agroweather.AgroWeatherUnavailable as e:
        raise HTTPException(503, "weather unavailable: no live source and no cached data") from e


@router.get("/farms/{farm_id}/weather")
def weather(farm_id: int, lang: str = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = _farm(db, farm_id)
    b = _bundle(farm)
    now = agroweather.now_ist()
    stage, das = kb.stage_for(farm.crop, farm.sowing_date, now.date())
    v = agromet.view(b, kb.agromet, farm.crop, stage, now, lang, sprays=notify.recent_sprays(db, farm, now),
                     needs_spray=notify.needs_spray(db, farm))
    risks = services.risk_scores(db, kb, farm, now.date(), services.weather_for(db, farm))
    return v | {
        "crop": {"id": farm.crop, "name": tr(kb.crops[farm.crop]["names"], lang), "stage": stage,
                 "stage_name": kb.stage_name(farm.crop, stage, lang), "das": das,
                 "kc": kb.agromet["kc"].get(farm.crop, {}).get(stage)},
        "watch_for": [{"target": s.target, "name": tr(kb.targets[s.target]["names"], lang), "level": s.level}
                      for s in risks[:4]],
        "location": {"lat": b["lat"], "lon": b["lon"], "district": farm.district},
        "seasonal": services.kcc_seasonal(kb, farm, now.month, lang),
        # The pH of the soil under this field: a sensor reading if there is one,
        # else the Soil Health Card value the farmer typed, else the ISRIC
        # SoilGrids estimate for the point. It was already read for the live walk
        # and never shown on a screen, so a farmer could not see the pH the app
        # was reasoning from. Merged into the soil block that already carries
        # temperature and moisture rather than replacing it.
        "soil": (v.get("soil") or {}) | {"ph": live.soil_ph_for(db, farm, b["lat"], b["lon"], lang)},
    }


@router.get("/farms/{farm_id}/satellite")
def satellite_view(farm_id: int, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    """Crop greenness (NDVI) from clear Sentinel-2 / Landsat 8 scenes and satellite
    soil data for this field. Numbers only — provider image URLs carry our key."""
    farm = _farm(db, farm_id)
    if not satellite.configured():
        return {"available": False, "reason": "not_configured"}
    now = agroweather.now_ist()
    try:
        s = watch.satellite_summary(db, kb, farm, now)
        db.commit()  # a newly created field polygon
        soil = satellite.soil(farm.agro_polygon_id) if farm.agro_polygon_id else None
    except satellite.SatelliteUnavailable:
        raise HTTPException(503, "satellite data unavailable right now") from None
    return s | {"soil": soil, "polygon_ha": round(max(farm.area_acres * 0.4047, satellite.MIN_HA), 2),
                "source": "AgroMonitoring — Sentinel-2 / Landsat 8"}


# --------------------------------------------------------------------------
# Notices
# --------------------------------------------------------------------------

@router.get("/farms/{farm_id}/notices")
def notices(farm_id: int, lang: str = "en", limit: int = 30, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = _farm(db, farm_id)
    now = agroweather.now_ist()
    rows = db.scalars(select(Notice).where(Notice.farm_id == farm.id)
                      .order_by(Notice.created_at.desc(), Notice.id.desc()).limit(min(limit, 100))).all()
    unread = db.scalar(select(func.count(Notice.id)).where(Notice.farm_id == farm.id, Notice.read_at.is_(None),
                                                           Notice.valid_until > now)) or 0
    return {"unread": unread, "items": [notify.notice_view(kb, farm, n, lang, now) for n in rows]}


class ReadIn(BaseModel):
    ids: list[int] | None = None


@router.post("/farms/{farm_id}/notices/read")
def mark_read(farm_id: int, body: ReadIn, db: Session = Depends(get_db)):
    farm = _farm(db, farm_id)
    q = select(Notice).where(Notice.farm_id == farm.id, Notice.read_at.is_(None))
    if body.ids:
        q = q.where(Notice.id.in_(body.ids))
    rows = db.scalars(q).all()
    for n in rows:
        n.read_at = datetime.now()
    db.commit()
    return {"marked": len(rows)}


@router.get("/farms/{farm_id}/events")
async def events(farm_id: int, request: Request, db: Session = Depends(get_db)):
    _farm(db, farm_id)
    db.close()  # the stream can stay open for hours; don't hold a connection

    async def stream():
        q = notify.broker.subscribe(farm_id)
        ends = asyncio.get_running_loop().time() + SSE_MAX_SECONDS
        try:
            yield "retry: 5000\n\n"
            # Bounded lifetime: EventSource reconnects by itself, and a server
            # restart or deploy never waits on a stream that is open for hours.
            while not await request.is_disconnected() and asyncio.get_running_loop().time() < ends:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"  # proxies close silent connections
        finally:
            notify.broker.unsubscribe(farm_id, q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------
# Web Push
# --------------------------------------------------------------------------

@router.get("/push/key")
def push_key():
    return {"public_key": notify.vapid_public_key()}


class Keys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000, pattern=r"^https://")
    keys: Keys


@router.post("/farms/{farm_id}/push/subscribe", status_code=201)
def subscribe(farm_id: int, body: SubscriptionIn, db: Session = Depends(get_db)):
    farm = _farm(db, farm_id)
    s = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if s is None:
        s = PushSubscription(endpoint=body.endpoint, farm_id=farm.id, p256dh=body.keys.p256dh, auth=body.keys.auth)
        db.add(s)
    else:  # same phone, maybe switched farm
        s.farm_id, s.p256dh, s.auth, s.failures = farm.id, body.keys.p256dh, body.keys.auth, 0
    db.commit()
    return {"subscribed": True}


class EndpointIn(BaseModel):
    endpoint: str


@router.post("/push/unsubscribe")
def unsubscribe(body: EndpointIn, db: Session = Depends(get_db)):
    s = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if s:
        db.delete(s)
        db.commit()
    return {"subscribed": False}


@router.post("/farms/{farm_id}/push/test")
def push_test(farm_id: int, lang: str | None = None, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = _farm(db, farm_id)
    rate_limit(f"push-test:{farm_id}", 10, 3600)
    lang = lang or farm.lang
    crop = tr(kb.crops[farm.crop]["names"], lang)
    out = notify.push(db, farm.id, {"title": tr(PUSH_TEST_TITLE, lang), "body": tr(PUSH_TEST_BODY, lang).format(crop=crop),
                                    "url": "/app/weather", "tag": "test", "severity": "info"})
    db.commit()
    return out


# --------------------------------------------------------------------------
# Spray log
# --------------------------------------------------------------------------

class SprayIn(BaseModel):
    product: str | None = Field(default=None, max_length=120)


@router.post("/farms/{farm_id}/sprays", status_code=201)
def log_spray(farm_id: int, body: SprayIn, lang: str = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = _farm(db, farm_id)
    rate_limit(f"spray:{farm_id}", 20, 3600)
    now = agroweather.now_ist()
    row = SprayLog(farm_id=farm.id, product=(body.product or "").strip() or None, sprayed_at=now)
    db.add(row)
    db.commit()
    check = None
    try:
        b = agroweather.bundle(farm.lat, farm.lon)
        hours = agromet.spray_hours(b, now, kb.agromet["spray"], horizon=1)
        if hours:
            h = hours[0]
            check = h | {"reasons_text": agromet.reason_text(h["reasons"], kb.agromet["words"], lang)
                         if h["reasons"] else None}
    except agroweather.AgroWeatherUnavailable:
        pass
    return {"id": row.id, "sprayed_at": now.isoformat(), "check": check}


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------

class ContactIn(BaseModel):
    email: str | None = Field(default=None, max_length=200)
    email_pref: str = "warnings"


def _contact(db: Session, farm: Farm) -> dict:
    phones = db.scalar(select(func.count(PushSubscription.id)).where(PushSubscription.farm_id == farm.id)) or 0
    return {"email": farm.email, "email_pref": farm.email_pref or "warnings", "phones": phones,
            "email_delivery": "live" if EMAIL_BACKEND == "smtp" else "outbox"}


@router.get("/farms/{farm_id}/contact")
def get_contact(farm_id: int, db: Session = Depends(get_db)):
    return _contact(db, _farm(db, farm_id))


@router.put("/farms/{farm_id}/contact")
def put_contact(farm_id: int, body: ContactIn, db: Session = Depends(get_db)):
    farm = _farm(db, farm_id)
    email = (body.email or "").strip() or None
    if email and not valid_address(email):
        raise HTTPException(422, "that does not look like an email address")
    if body.email_pref not in EMAIL_PREFS:
        raise HTTPException(422, f"email_pref must be one of {EMAIL_PREFS}")
    if email != farm.email:
        farm.email_token = None  # a new address gets a new unsubscribe secret
    farm.email, farm.email_pref = email, body.email_pref
    notify.ensure_token(farm)
    db.commit()
    return _contact(db, farm)


@router.post("/farms/{farm_id}/email/test")
def email_test(farm_id: int, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = _farm(db, farm_id)
    if not farm.email:
        raise HTTPException(409, "add an email address first")
    rate_limit(f"email-test:{farm_id}", 5, 3600)
    try:
        b = agroweather.bundle(farm.lat, farm.lon)
    except agroweather.AgroWeatherUnavailable:
        b = None
    status, err = notify.email_test(db, kb, farm, b, agroweather.now_ist())
    db.commit()
    if status == "failed":
        raise HTTPException(502, f"email not sent ({err})")
    return {"status": status}


@router.post("/farms/{farm_id}/email/summary")
def email_summary(farm_id: int, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = _farm(db, farm_id)
    if not farm.email:
        raise HTTPException(409, "add an email address first")
    rate_limit(f"email-summary:{farm_id}", 5, 3600)
    status = notify.email_digest(db, kb, farm, _bundle(farm), agroweather.now_ist(), manual=True)
    db.commit()
    if status == "failed":
        raise HTTPException(502, "email not sent")
    return {"status": status}


UNSUB_PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>AnnRakshak</title><body style="font-family:system-ui,sans-serif;background:#f7f3ec;color:#2b1d12;padding:32px">
<div style="max-width:420px;margin:auto;background:#fff;border-radius:16px;padding:24px;border:1px solid #e6dfd3">
<p style="font-size:18px;font-weight:600;color:#1f3d2b">AnnRakshak</p><p>{msg}</p></div></body>"""


def _unsubscribe(token: str, db: Session) -> str:
    farm = db.scalar(select(Farm).where(Farm.email_token == token)) if token and len(token) >= 16 else None
    if farm is None:
        return "This link has expired or was already used. You can change emails in the app under Alerts."
    farm.email_pref = "off"
    db.commit()
    return ("You will not get AnnRakshak emails any more. / आपको अब AnnRakshak ईमेल नहीं मिलेंगे। / "
            "तुम्हाला आता AnnRakshak ईमेल येणार नाहीत.")


@router.get("/email/unsubscribe", response_class=HTMLResponse)
def unsubscribe_link(token: str = "", db: Session = Depends(get_db)):
    return UNSUB_PAGE.format(msg=_unsubscribe(token, db))


@router.post("/email/unsubscribe", response_class=HTMLResponse)
def unsubscribe_one_click(token: str = "", db: Session = Depends(get_db)):
    return UNSUB_PAGE.format(msg=_unsubscribe(token, db))


# --------------------------------------------------------------------------
# Ops
# --------------------------------------------------------------------------

@router.post("/officials/watch/run", dependencies=[Depends(auth.require("expert"))])
async def watch_run():
    return await run_in_threadpool(watch.cycle)
