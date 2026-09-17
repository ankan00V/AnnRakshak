"""Getting a notice to the farmer: in the open app (Server-Sent Events), on the
phone when the app is closed (Web Push), and by email.

Delivery policy, in one place:
- In-app: everything, the moment it is issued.
- Phone: warnings always; other notices wait out the quiet hours (21:00–06:00)
  and stop at MAX_PUSH_PER_FARM_PER_DAY. A notice past its validity is never sent late.
- Email: per the farmer's choice — warnings and new high-risk alerts for their
  crop right away ('warnings', the default), every advisory ('all'), or only the
  6 am summary ('digest'). At most MAX_ALERT_EMAILS_PER_FARM_PER_DAY alert emails.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
from datetime import date, datetime, timedelta
from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cache, live, mailer, services
from app.config import (
    DATA_DIR,
    MAX_ALERT_EMAILS_PER_FARM_PER_DAY,
    MAX_PUSH_PER_FARM_PER_DAY,
    PUBLIC_APP_URL,
    QUIET_HOURS,
    VAPID_PRIVATE_KEY,
    VAPID_SUBJECT,
)
from app.engine import agromet, risk
from app.kb import KB, tr, trl
from app.models import Alert, EmailLog, Farm, Notice, Problem, PushSubscription, SprayLog

LEVEL_LABEL = {
    "high": {"en": "High risk", "hi": "अधिक जोखिम", "mr": "जास्त धोका"},
    "medium": {"en": "Medium risk", "hi": "मध्यम जोखिम", "mr": "मध्यम धोका"},
    "low": {"en": "Low risk", "hi": "कम जोखिम", "mr": "कमी धोका"},
}
ALERT_TITLE = {"en": "Field check: {name} — {level}", "hi": "खेत जाँच: {name} — {level}",
               "mr": "शेत तपासणी: {name} — {level}"}


# --------------------------------------------------------------------------
# In-app: Server-Sent Events broker
# --------------------------------------------------------------------------

class Broker:
    """Per-farm fan-out to open app tabs. publish() is safe from worker threads
    (the watcher and sync endpoints run in the threadpool)."""

    def __init__(self) -> None:
        self._subs: dict[int, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}

    def subscribe(self, farm_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subs.setdefault(farm_id, set()).add((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, farm_id: int, q: asyncio.Queue) -> None:
        self._subs[farm_id] = {(lp, x) for lp, x in self._subs.get(farm_id, set()) if x is not q}

    def listeners(self, farm_id: int) -> int:
        return len(self._subs.get(farm_id, ()))

    def publish(self, farm_id: int, event: dict) -> int:
        """To every instance's tabs via Redis when it is up; else to this instance's."""
        if cache.publish(farm_id, event):
            return -1  # relayed; each instance's listener delivers locally
        return self.deliver_local(farm_id, event)

    def deliver_local(self, farm_id: int, event: dict) -> int:
        n = 0
        for loop, q in list(self._subs.get(farm_id, ())):
            def put(q=q):
                if not q.full():  # a stalled tab loses events rather than growing memory
                    q.put_nowait(event)
            try:
                loop.call_soon_threadsafe(put)
                n += 1
            except RuntimeError:  # that tab's loop is gone
                self.unsubscribe(farm_id, q)
        return n


broker = Broker()


# --------------------------------------------------------------------------
# Phone: Web Push (VAPID)
# --------------------------------------------------------------------------

@lru_cache
def vapid() -> Vapid02:
    """Our VAPID key pair. From .env when set; otherwise generated once into the
    data directory (private to this server; never sent anywhere)."""
    if VAPID_PRIVATE_KEY:
        return Vapid02.from_pem(VAPID_PRIVATE_KEY.replace("\\n", "\n").encode())
    path = DATA_DIR / "vapid_private.pem"
    if path.exists():
        return Vapid02.from_file(str(path))
    v = Vapid02()
    v.generate_keys()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(v.private_pem())
    os.chmod(path, 0o600)
    return v


def vapid_public_key() -> str:
    raw = vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def push(db: Session, farm_id: int, payload: dict) -> dict:
    """Send to every subscribed browser of this farm. Gone endpoints (404/410) are
    removed; one that keeps failing is dropped after 5 tries."""
    out = {"sent": 0, "removed": 0, "failed": 0}
    for s in db.scalars(select(PushSubscription).where(PushSubscription.farm_id == farm_id)).all():
        try:
            webpush({"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                    json.dumps(payload, ensure_ascii=False), vapid_private_key=vapid(),
                    vapid_claims={"sub": VAPID_SUBJECT}, ttl=6 * 3600, timeout=10)
            s.last_ok_at, s.failures = datetime.now(), 0
            out["sent"] += 1
        except WebPushException as e:
            status = e.response.status_code if e.response is not None else None
            if status in (404, 410):
                db.delete(s)
                out["removed"] += 1
            else:
                s.failures += 1
                if s.failures >= 5:
                    db.delete(s)
                    out["removed"] += 1
                out["failed"] += 1
        except Exception:  # noqa: BLE001  a broken push service must not stop the watcher
            s.failures += 1
            out["failed"] += 1
    return out


# --------------------------------------------------------------------------
# Rendering notices and alerts
# --------------------------------------------------------------------------

def _adv(n: Notice) -> dict:
    return {"rule": n.rule, "severity": n.severity, "category": n.category, "notify": True,
            "key": n.dedupe_key, "values": n.values, "valid_until": n.valid_until.strftime("%Y-%m-%dT%H:%M")}


def notice_view(kb: KB, farm: Farm, n: Notice, lang: str, now: datetime) -> dict:
    r = agromet.render(_adv(n), kb.agromet, lang, farm.crop, now)
    return r | {"notice_id": n.id, "created_at": n.created_at.isoformat(), "read": n.read_at is not None,
                "active": n.valid_until > now}


def alert_card(kb: KB, a: Alert, lang: str) -> dict:
    name = tr(kb.targets[a.target]["names"], lang)
    level = tr(LEVEL_LABEL.get(a.level, LEVEL_LABEL["medium"]), lang)
    prev = live.prevention_for(kb, a.target, lang)
    return {"title": tr(ALERT_TITLE, lang).format(name=name, level=level), "text": risk.reason_text(a.reason, lang),
            "do": trl(a.tasks, lang)[:2] + prev["do"][:1], "severity": "warning" if a.level == "high" else "advice"}


def _payload(title: str, body: str, url: str, tag: str, severity: str) -> dict:
    return {"title": title, "body": body[:240], "url": url, "tag": tag, "severity": severity}


def quiet(now: datetime) -> bool:
    start, end = QUIET_HOURS
    return now.hour >= start or now.hour < end


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------

def publish_new(kb: KB, farm: Farm, notices: list[Notice], alerts: list[Alert], now: datetime) -> None:
    for n in notices:
        v = notice_view(kb, farm, n, farm.lang, now)
        broker.publish(farm.id, {"type": "notice", "id": n.id, "severity": n.severity, "title": v["title"],
                                 "body": v["text"], "url": "/app/weather"})
    for a in alerts:
        c = alert_card(kb, a, farm.lang)
        broker.publish(farm.id, {"type": "alert", "id": a.id, "severity": c["severity"], "title": c["title"],
                                 "body": c["text"], "url": "/app/alerts"})


def deliver_push(db: Session, kb: KB, farm: Farm, now: datetime) -> int:
    """Phone notifications for notices and alerts not yet handled on this channel."""
    today = now.date()
    pending = db.scalars(select(Notice).where(
        Notice.farm_id == farm.id, Notice.pushed_at.is_(None), Notice.valid_until > now,
        Notice.created_at >= datetime.combine(today - timedelta(days=1), datetime.min.time()),
    ).order_by(Notice.id)).all()
    alerts = db.scalars(select(Alert).where(
        Alert.farm_id == farm.id, Alert.notified_at.is_(None), Alert.issued_on >= today - timedelta(days=1),
        Alert.outcome.is_(None),
    )).all()
    has_subs = db.scalar(select(func.count(PushSubscription.id)).where(PushSubscription.farm_id == farm.id)) or 0
    sent_today = db.scalar(select(func.count(Notice.id)).where(
        Notice.farm_id == farm.id, Notice.pushed_at >= datetime.combine(today, datetime.min.time()),
        Notice.severity != "warning")) or 0
    sent = 0
    for n in pending:
        urgent = n.severity == "warning"
        if not urgent and (quiet(now) or sent_today >= MAX_PUSH_PER_FARM_PER_DAY):
            continue  # waits for morning, or for tomorrow's allowance
        if has_subs:
            v = notice_view(kb, farm, n, farm.lang, now)
            push(db, farm.id, _payload(v["title"], v["text"], "/app/weather", n.dedupe_key, n.severity))
            sent += 1
        n.pushed_at = now
        sent_today += not urgent
    for a in alerts:
        if a.level != "high" and quiet(now):
            continue
        if has_subs:
            c = alert_card(kb, a, farm.lang)
            push(db, farm.id, _payload(c["title"], c["text"], "/app/alerts", f"alert:{a.id}", c["severity"]))
            sent += 1
        a.notified_at = datetime.now()
    return sent


def app_url(path: str = "/app/weather") -> str:
    return f"{PUBLIC_APP_URL}{path}"


def unsubscribe_url(farm: Farm) -> str:
    return f"{PUBLIC_APP_URL}/api/email/unsubscribe?token={farm.email_token}"


def ensure_token(farm: Farm) -> None:
    if not farm.email_token:
        farm.email_token = secrets.token_urlsafe(24)


def digest_data(db: Session, kb: KB, farm: Farm, bundle: dict, now: datetime) -> dict:
    """Everything the email says, from the farm profile and live data."""
    lang = farm.lang
    stage, das = kb.stage_for(farm.crop, farm.sowing_date, now.date())
    sprays = recent_sprays(db, farm, now)
    needs = needs_spray(db, farm)
    view = agromet.view(bundle, kb.agromet, farm.crop, stage, now, lang, sprays=sprays, needs_spray=needs)
    words = kb.agromet["words"]
    days3 = [d | {"label": agromet.day_word(date.fromisoformat(d["on"]), now.date(), words, lang)} for d in view["daily"][:3]]
    spray_label = None
    for w in view["spray"]["windows"]:
        st = datetime.fromisoformat(w["start"])
        spray_label = f"{agromet.day_word(st.date(), now.date(), words, lang)} {st:%H:%M}–{w['end'][11:16]}"
        break
    ph = live.soil_ph_for(db, farm, farm.lat, farm.lon, lang)
    sensor_m = live.soil_moisture_for(db, farm, None)
    moist = sensor_m["value_pct"] if sensor_m else next(
        (m["pct"] for m in (view["soil"] or {}).get("moisture", []) if m["depth"].startswith("9") and m["pct"] is not None), None)
    risks = []
    window = services.weather_for(db, farm)
    for s in services.risk_scores(db, kb, farm, now.date(), window)[:3]:
        risks.append({"name": tr(kb.targets[s.target]["names"], lang), "level": s.level,
                      "level_label": tr(LEVEL_LABEL[s.level], lang), "reason": risk.reason_text(s.reason, lang),
                      "prevention": live.prevention_for(kb, s.target, lang)})
    ensure_token(farm)
    return {
        "farm": {"name": farm.farmer_name, "crop_name": tr(kb.crops[farm.crop]["names"], lang),
                 "district": farm.district, "sowing": farm.sowing_date.strftime("%d-%m-%Y"),
                 "stage_name": kb.stage_name(farm.crop, stage, lang), "das": das},
        "weather": view, "days3": days3, "spray_label": spray_label, "ph": ph, "moisture_pct": moist,
        "risks": risks, "source": bundle["source"]["forecast"], "date_label": now.strftime("%d-%m-%Y"),
        "app_url": app_url(), "unsubscribe_url": unsubscribe_url(farm),
    }


def _log(db: Session, farm: Farm, kind: str, key: str, subject: str, status: str, error: str | None) -> EmailLog:
    row = EmailLog(farm_id=farm.id, kind=kind, dedupe_key=key, to_addr=farm.email, subject=subject[:300],
                   status=status, error=error, sent_at=datetime.now())
    db.add(row)
    db.flush()
    return row


def email_alerts(db: Session, kb: KB, farm: Farm, bundle: dict, now: datetime) -> str | None:
    """One email with every warning (and new high-risk alert) not yet emailed."""
    if not farm.email or farm.email_pref not in ("warnings", "all"):
        return None
    levels = ("warning", "advice") if farm.email_pref == "all" else ("warning",)
    notices = db.scalars(select(Notice).where(
        Notice.farm_id == farm.id, Notice.emailed_at.is_(None), Notice.valid_until > now,
        Notice.severity.in_(levels), Notice.created_at >= datetime.combine(now.date(), datetime.min.time()),
    ).order_by(Notice.id)).all()
    if quiet(now):
        notices = [n for n in notices if n.severity == "warning"]
    alerts = db.scalars(select(Alert).where(
        Alert.farm_id == farm.id, Alert.level == "high", Alert.issued_on == now.date(), Alert.outcome.is_(None),
        Alert.emailed_at.is_(None),
    )).all()
    if not notices and not alerts:
        return None
    sent_today = db.scalar(select(func.count(EmailLog.id)).where(
        EmailLog.farm_id == farm.id, EmailLog.kind == "alert",
        EmailLog.sent_at >= datetime.combine(now.date(), datetime.min.time()))) or 0
    if sent_today >= MAX_ALERT_EMAILS_PER_FARM_PER_DAY:
        return None
    d = digest_data(db, kb, farm, bundle, now)
    advs = [notice_view(kb, farm, n, farm.lang, now) for n in notices] + [alert_card(kb, a, farm.lang) for a in alerts]
    subject, text, html = mailer.alert(d, advs, farm.lang)
    status, err = mailer.send(farm.email, subject, text, html, unsubscribe_url=d["unsubscribe_url"])
    ids = ",".join([f"n{n.id}" for n in notices] + [f"a{a.id}" for a in alerts])
    _log(db, farm, "alert", f"alert:{now:%Y%m%d%H%M%S}:{ids}"[:80], subject, status, err)
    if status != "failed":
        for x in [*notices, *alerts]:
            x.emailed_at = now
    return status


def email_digest(db: Session, kb: KB, farm: Farm, bundle: dict, now: datetime, *, manual: bool = False) -> str | None:
    if not farm.email or (farm.email_pref == "off" and not manual):
        return None
    key = f"digest:{now.date()}" if not manual else f"digest-manual:{now:%Y%m%d%H%M%S}"
    if not manual and db.scalar(select(EmailLog.id).where(EmailLog.farm_id == farm.id, EmailLog.dedupe_key == key)):
        return None
    d = digest_data(db, kb, farm, bundle, now)
    subject, text, html = mailer.digest(d, farm.lang)
    status, err = mailer.send(farm.email, subject, text, html, unsubscribe_url=d["unsubscribe_url"])
    _log(db, farm, "digest", key, subject, status, err)
    return status


def email_test(db: Session, kb: KB, farm: Farm, bundle: dict | None, now: datetime) -> tuple[str, str | None]:
    ensure_token(farm)
    d = {"farm": {"name": farm.farmer_name, "crop_name": tr(kb.crops[farm.crop]["names"], farm.lang),
                  "district": farm.district}, "app_url": app_url(), "unsubscribe_url": unsubscribe_url(farm),
         "source": (bundle or {}).get("source", {}).get("forecast", "Open-Meteo")}
    subject, text, html = mailer.test_message(d, farm.lang)
    status, err = mailer.send(farm.email, subject, text, html, unsubscribe_url=d["unsubscribe_url"])
    _log(db, farm, "test", f"test:{now:%Y%m%d%H%M%S}", subject, status, err)
    return status, err


# --------------------------------------------------------------------------
# Farm context the rules need
# --------------------------------------------------------------------------

def recent_sprays(db: Session, farm: Farm, now: datetime) -> list[dict]:
    rows = db.scalars(select(SprayLog).where(SprayLog.farm_id == farm.id,
                                             SprayLog.sprayed_at >= now - timedelta(hours=24))).all()
    return [{"id": r.id, "at": r.sprayed_at, "product": r.product} for r in rows]


def needs_spray(db: Session, farm: Farm) -> bool:
    """Only a farm with an open problem is told 'no good time to spray'."""
    return bool(db.scalar(select(Problem.id).where(Problem.farm_id == farm.id, Problem.status == "open").limit(1)))
