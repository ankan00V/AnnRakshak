"""The background watcher: every WATCH_MINUTES, for every farm —

  1. hour-by-hour agro-weather (one batched fetch per grid cell, cached);
  2. the weather rules for this crop at this stage (app.engine.agromet) ->
     new notices, one per farm, rule and day (unique constraint, not a SELECT race);
  3. the crop's pest and disease risk rules (services.run_risk) -> alerts;
  4. delivery: in-app at once, phone and email per app.notify's policy;
  5. the 6 am summary email.

One failing farm never stops the sweep. In production run exactly one watcher
(ANNRAKSHAK_WATCH=off on the other API workers): notices are deduplicated by
constraint, but two watchers could each push the same notice.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import cache, notify, services
from app.config import DIGEST_HOUR, WATCH_MINUTES
from app.db import SessionLocal
from app.engine import agromet, agroweather, satellite
from app.kb import KB, get_kb
from app.models import Alert, Farm, Notice

log = logging.getLogger("annrakshak.watch")


def issue_notices(db: Session, kb: KB, farm: Farm, bundle: dict | None, now: datetime,
                  extra: list[dict] | None = None) -> list[Notice]:
    stage, _ = kb.stage_of(farm, now.date())
    advs = agromet.evaluate(bundle, kb.agromet, farm.crop, stage, now,
                            sprays=notify.recent_sprays(db, farm, now),
                            needs_spray=notify.needs_spray(db, farm)) if bundle else []
    advs += extra or []
    have = set(db.scalars(select(Notice.dedupe_key).where(Notice.farm_id == farm.id)).all())
    new = []
    for a in advs:
        if not a["notify"] or a["key"] in have:
            continue
        n = Notice(farm_id=farm.id, rule=a["rule"], severity=a["severity"], category=a["category"],
                   dedupe_key=a["key"], values=a["values"], valid_until=datetime.fromisoformat(a["valid_until"]),
                   created_at=now)
        try:
            with db.begin_nested():
                db.add(n)
            new.append(n)
        except IntegrityError:  # another watcher got there first
            pass
    return new


def ensure_polygon(db: Session, farm: Farm) -> str | None:
    """Create the farm's field polygon at the satellite provider once."""
    if farm.agro_polygon_id or not satellite.configured():
        return farm.agro_polygon_id
    ha = farm.area_acres * 0.4047
    p = satellite.create_polygon(f"annrakshak-farm-{farm.id}", farm.lat, farm.lon, ha)
    farm.agro_polygon_id = p["id"]
    db.flush()
    return farm.agro_polygon_id


def satellite_summary(db: Session, kb: KB, farm: Farm, now: datetime) -> dict:
    stage, _ = kb.stage_of(farm, now.date())
    polyid = ensure_polygon(db, farm)
    if not polyid:
        return {"available": False, "reason": "not configured"}
    return satellite.summarize(satellite.ndvi_series(polyid, now.date()), farm.crop, stage, now.date())


def satellite_advisory(db: Session, kb: KB, farm: Farm, now: datetime) -> dict | None:
    if not satellite.configured():
        return None
    try:
        return satellite.evaluate(satellite_summary(db, kb, farm, now), now)
    except satellite.SatelliteUnavailable as e:
        log.info("watch: satellite for farm %s: %s", farm.id, e)
        return None


def farm_cycle(db: Session, kb: KB, farm: Farm, now: datetime, fetch=agroweather.bundle) -> dict:
    out = Counter()
    try:
        bundle = fetch(farm.lat, farm.lon)
    except agroweather.AgroWeatherUnavailable:
        out["no_weather"] += 1
        bundle = None
    sat_summary = None
    if satellite.configured():
        try:
            sat_summary = satellite_summary(db, kb, farm, now)
        except satellite.SatelliteUnavailable as e:
            log.info("watch: satellite for farm %s: %s", farm.id, e)
    sat = satellite.evaluate(sat_summary, now) if sat_summary else None
    out["satellite"] += sat is not None
    new = issue_notices(db, kb, farm, bundle, now, [sat] if sat else [])
    out["notices"] += len(new)
    before = set(db.scalars(select(Alert.id).where(Alert.farm_id == farm.id)).all())
    services.run_risk(db, kb, farm, now.date(),
                      satellite=services.satellite_drop(sat_summary))
    new_alerts = db.scalars(select(Alert).where(Alert.farm_id == farm.id, Alert.id.not_in(list(before) or [0]))).all()
    out["alerts"] += len(new_alerts)
    notify.publish_new(kb, farm, new, list(new_alerts), now)
    out["pushed"] += notify.deliver_push(db, kb, farm, now)
    if bundle and farm.email:
        if notify.email_alerts(db, kb, farm, bundle, now):
            out["alert_emails"] += 1
        if now.hour >= DIGEST_HOUR and farm.email_pref != "off" and notify.email_digest(db, kb, farm, bundle, now):
            out["digests"] += 1
    db.commit()
    return out


def cycle(db: Session | None = None, kb: KB | None = None, now: datetime | None = None,
          fetch=agroweather.bundle) -> dict:
    own = db is None
    db = db or SessionLocal()
    kb = kb or get_kb()
    now = now or agroweather.now_ist()
    stats = Counter()
    try:
        farms = db.scalars(select(Farm)).all()
        if fetch is agroweather.bundle:
            agroweather.prefetch([(f.lat, f.lon) for f in farms])
        for farm in farms:
            try:
                stats.update(farm_cycle(db, kb, farm, now, fetch))
            except Exception:  # noqa: BLE001  one bad farm must not stop the sweep
                db.rollback()
                stats["errors"] += 1
                log.exception("watch: farm %s failed", farm.id)
        stats["farms"] = len(farms)
    finally:
        if own:
            db.close()
    return dict(stats) | {"at": now.isoformat()}


async def run_forever() -> None:
    """Started by the app's lifespan. First sweep shortly after start-up."""
    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415

    await asyncio.sleep(10)
    while True:
        try:
            # Many API instances, one watcher: the lease outlives a sweep interval
            # so the leader keeps it; if the leader dies another takes over.
            if cache.leader("watch", WATCH_MINUTES * 60 + 120):
                stats = await run_in_threadpool(cycle)
                log.info("watch: %s", stats)
        except Exception:  # noqa: BLE001
            log.exception("watch: sweep failed")
        await asyncio.sleep(timedelta(minutes=WATCH_MINUTES).total_seconds())
