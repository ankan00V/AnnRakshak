"""Rain that actually fell on the field, from ISRO's INSAT-3DS satellite (MOSDAC).

Weather models say what rain *should* have fallen. The INSAT-3DS Hydro-Estimator
(HEM, product 3SIMG_L2B_HEM, Space Applications Centre / ISRO) measures rain
rate over India every 30 minutes at about 4 km. This module fetches each new
file, reads the rain rate at every farm's spot, keeps only those numbers
(table sat_rain) and deletes the file. Past days' rain in the weather — and so
the irrigation water balance and the pest and disease rules — then use what was
observed instead of what was modelled, once enough of the day is covered.

API (https://mosdac.gov.in/downloadapi-manual):
  search    GET  /apios/datasets.json      no login
  token     POST /download_api/gettoken    MOSDAC account (MOSDAC_USERNAME / _PASSWORD)
  download  GET  /download_api/download?id  Bearer token
Limits honoured: 5000 files a day per user (we take at most 48), and three bad
logins lock the account for an hour — so after one refused login we stop
trying until the credentials change.

Nothing here raises into a request: without an account, or when MOSDAC is down,
the app simply keeps the modelled rain and says so.
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import cache
from app.config import BACKEND_DIR, MOSDAC_DATASET, MOSDAC_PASSWORD, MOSDAC_USERNAME
from app.db import SessionLocal
from app.models import Farm, SatRain

log = logging.getLogger("annrakshak.mosdac")

BASE = "https://mosdac.gov.in"
SEARCH_URL = f"{BASE}/apios/datasets.json"
TOKEN_URL = f"{BASE}/download_api/gettoken"
DOWNLOAD_URL = f"{BASE}/download_api/download"
LOGOUT_URL = f"{BASE}/download_api/logout"
INDIA_BBOX = "68.0,6.0,98.0,37.5"
SOURCE = "INSAT-3DS Hydro-Estimator rainfall (MOSDAC, SAC-ISRO)"

CYCLE_MINUTES = 30
PER_CYCLE = 12
"""Files fetched per cycle (~9.5 MB each). The first run backfills the last day
over a few cycles instead of pulling half a gigabyte at once."""
LOOKBACK_H = 26
MIN_COVERAGE = 0.5
"""A day's satellite total replaces the model's only when at least half of its
30-minute slots were read: the average rate over the slots we have, times 24 h."""
MAX_PIXEL_DEG = 0.1
TIMEOUT_S = 60.0
WORK_DIR = BACKEND_DIR / ".data" / "mosdac"
IST = timezone(timedelta(hours=5, minutes=30))

_state: dict = {"last_run": None, "last_granule": None, "error": None, "files": 0, "locked_out": False}


def configured() -> bool:
    return bool(MOSDAC_USERNAME and MOSDAC_PASSWORD)


def status() -> dict:
    return {"configured": configured(), "dataset": MOSDAC_DATASET, **_state}


def point_key(lat: float, lon: float) -> tuple[float, float]:
    """Farms within ~1 km share a pixel read (the product is ~4 km)."""
    return round(lat, 2), round(lon, 2)


# --------------------------------------------------------------------------
# Search (no login)
# --------------------------------------------------------------------------

_SLOT = re.compile(r"_(\d{2}[A-Z]{3}\d{4})_(\d{4})_")


def slot_of(entry: dict) -> datetime | None:
    """The granule's UTC time, from 'updated' or else its file name
    (3SIMG_21SEP2026_1530_L2B_HEM_V01R00.h5)."""
    u = entry.get("updated")
    if u:
        try:
            return datetime.strptime(u, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    m = _SLOT.search(entry.get("identifier") or "")
    if m:
        return datetime.strptime(m.group(1) + m.group(2), "%d%b%Y%H%M").replace(tzinfo=timezone.utc)
    return None


def search(start: date, end: date, *, dataset: str = MOSDAC_DATASET, count: int = 100,
           client: httpx.Client | None = None) -> list[dict]:
    """Granules over India between two dates, newest first."""
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S)
    out: list[dict] = []
    try:
        index = 1
        while True:
            r = client.get(SEARCH_URL, params={"datasetId": dataset, "startTime": start.isoformat(),
                                               "endTime": end.isoformat(), "count": count,
                                               "boundingBox": INDIA_BBOX, "startIndex": index})
            if r.status_code == 500:  # MOSDAC's "Data unavailable for given parameters"
                break
            r.raise_for_status()
            page = r.json()
            entries = page.get("entries") or []
            out += entries
            if not entries or len(out) >= int(page.get("totalResults") or 0):
                break
            index += len(entries)
    finally:
        if own:
            client.close()
    return sorted((e for e in out if slot_of(e)), key=slot_of, reverse=True)


# --------------------------------------------------------------------------
# Download (MOSDAC account)
# --------------------------------------------------------------------------

class LoginRefused(Exception):
    pass


def _token(client: httpx.Client) -> str:
    r = client.post(TOKEN_URL, json={"username": MOSDAC_USERNAME, "password": MOSDAC_PASSWORD})
    if r.status_code in (400, 401):
        raise LoginRefused(f"MOSDAC refused the login ({r.status_code})")
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise LoginRefused("MOSDAC returned no token")
    return token


def _download(client: httpx.Client, token: str, entry: dict, dest: Path) -> Path:
    path = dest / Path(entry.get("identifier") or f"{entry['id']}.h5").name
    tmp = path.with_suffix(".part")
    with client.stream("GET", DOWNLOAD_URL, params={"id": entry["id"]},
                       headers={"Authorization": f"Bearer {token}"}) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.rename(path)
    return path


# --------------------------------------------------------------------------
# Reading a granule
# --------------------------------------------------------------------------

def _datasets(h5) -> dict[str, object]:
    found: dict[str, object] = {}

    def seen(name, obj) -> None:  # must return None: any other value stops the walk
        if hasattr(obj, "shape"):
            found.setdefault(name.split("/")[-1], obj)

    h5.visititems(seen)
    return found


def _pick(found: dict, patterns: list[str]):
    for p in patterns:
        for name, ds in found.items():
            if re.fullmatch(p, name, re.I):
                return ds
    return None


def _values(ds) -> np.ndarray:
    """Physical values: fill values NaN, then scale and offset applied."""
    a = np.asarray(ds[()], dtype="float64")
    attrs = {k.lower(): v for k, v in ds.attrs.items()}
    for key in ("_fillvalue", "missing_value", "fillvalue"):
        if key in attrs:
            fill = np.ravel(attrs[key])[0]
            a[a == fill] = np.nan
    scale = float(np.ravel(attrs.get("scale_factor", [1.0]))[0])
    offset = float(np.ravel(attrs.get("add_offset", [0.0]))[0])
    a = a * scale + offset
    return np.squeeze(a)


def read_rain(path: Path, points: list[tuple[float, float]]) -> list[float | None]:
    """Rain rate (mm/h) at each point: the nearest pixel within MAX_PIXEL_DEG,
    else None (off the disc, no data, or no pixel close enough)."""
    import h5py  # only needed where the ingest runs

    with h5py.File(path, "r") as h5:
        found = _datasets(h5)
        rain = _pick(found, [r"HEM", r".*rain.*rate.*", r".*precip.*", r".*rain.*"])
        lat = _pick(found, [r"Latitude", r"lat"])
        lon = _pick(found, [r"Longitude", r"lon"])
        if rain is None or lat is None or lon is None:
            raise ValueError(f"unrecognised HEM layout: {sorted(found)}")
        r, la, lo = _values(rain), _values(lat), _values(lon)

    if la.ndim == 1 and lo.ndim == 1:  # a regular latitude/longitude grid
        la, lo = np.meshgrid(la, lo, indexing="ij")
    if la.shape != r.shape or lo.shape != r.shape:
        raise ValueError(f"rain {r.shape} and lat/lon {la.shape}/{lo.shape} do not line up")

    out: list[float | None] = []
    for plat, plon in points:
        near = (np.abs(la - plat) <= MAX_PIXEL_DEG) & (np.abs(lo - plon) <= MAX_PIXEL_DEG)
        if not near.any():
            out.append(None)
            continue
        idx = np.flatnonzero(near)
        d2 = (la.flat[idx] - plat) ** 2 + ((lo.flat[idx] - plon) * np.cos(np.radians(plat))) ** 2
        v = r.flat[idx[int(np.argmin(d2))]]
        out.append(None if np.isnan(v) else round(float(max(0.0, v)), 2))
    return out


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------

def _points(db: Session) -> list[tuple[float, float]]:
    return sorted({point_key(lat, lon) for lat, lon in db.execute(select(Farm.lat, Farm.lon)).all()})


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _read_so_far(db: Session, since: datetime) -> dict[tuple[float, float], set[datetime]]:
    """For every spot, the image times already read there."""
    out: dict[tuple[float, float], set[datetime]] = {}
    for lat, lon, slot in db.execute(select(SatRain.lat, SatRain.lon, SatRain.slot).where(
            SatRain.dataset == MOSDAC_DATASET, SatRain.slot >= since)).all():
        out.setdefault((lat, lon), set()).add(_utc(slot))
    return out


_tried: set[tuple[tuple[float, float], datetime]] = set()
"""(spot, image) pairs already fetched for a spot that the image did not cover
(off the disc, no data): never fetched again for it."""


def ingest(db: Session, now: datetime | None = None, *, client: httpx.Client | None = None) -> dict:
    """One cycle. New images from the last day are read at every farm spot;
    then a spot that is behind — a farm added since those images came — has
    the images it missed fetched again and read there, so a new farmer sees
    the last day's rain within minutes, not only rain from here on. At most
    PER_CYCLE downloads a cycle; "more" says whether work is left."""
    now = now or datetime.now(timezone.utc)
    if not configured() or _state["locked_out"]:
        return {"skipped": "not configured" if not configured() else "login refused"}
    since = now - timedelta(hours=LOOKBACK_H)
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S, follow_redirects=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    stored = 0
    try:
        entries = [e for e in search((since - timedelta(days=1)).date(), now.date() + timedelta(days=1), client=client)
                   if slot_of(e) >= since]
        points = _points(db)
        seen = _read_so_far(db, since)
        done = set().union(*seen.values()) if seen else set()
        # (image, spots to read it at): new images at every spot, then images
        # a spot missed — newest first, so the last hours fill in first.
        work: list[tuple[dict, list[tuple[float, float]]]] = []
        for e in entries:
            slot = slot_of(e)
            spots = points if slot not in done else [
                p for p in points if slot not in seen.get(p, set()) and (p, slot) not in _tried]
            if spots:
                work.append((e, spots))
        todo, more = work[:PER_CYCLE], len(work) > PER_CYCLE
        if todo and points:
            token = _token(client)
            with tempfile.TemporaryDirectory(dir=WORK_DIR) as tmp:
                for e, spots in todo:
                    path = _download(client, token, e, Path(tmp))
                    rates = read_rain(path, spots)
                    path.unlink(missing_ok=True)  # keep the numbers, not the 10 MB file
                    slot = slot_of(e)
                    for spot, rate in zip(spots, rates):
                        _tried.add((spot, slot))
                        if rate is not None:
                            db.add(SatRain(dataset=MOSDAC_DATASET, lat=spot[0], lon=spot[1], slot=slot, mm_h=rate))
                            stored += 1
                    try:
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                    _state["last_granule"] = slot.isoformat()
            try:
                client.post(LOGOUT_URL, json={"username": MOSDAC_USERNAME}, timeout=10)
            except httpx.HTTPError:
                pass
        _state.update(error=None, files=_state["files"] + len(todo))
        return {"found": len(entries), "fetched": len(todo), "stored": stored, "more": more}
    except LoginRefused as e:
        _state.update(error=str(e), locked_out=True)  # never risk the one-hour lockout
        log.warning("%s; satellite rain stays off until the credentials change", e)
        return {"error": str(e)}
    except (httpx.HTTPError, OSError, ValueError, KeyError) as e:
        _state["error"] = f"{type(e).__name__}: {e}"[:300]
        log.warning("MOSDAC cycle failed: %s", _state["error"])
        return {"error": _state["error"]}
    finally:
        _state["last_run"] = now.isoformat()
        if own:
            client.close()


LEASE_S = 180
"""The ingest lease is short and renewed every minute while held, so a
restarted server takes over in a minute or two — a 30-minute lease left by a
killed process had kept the job from running at all."""


async def run_forever() -> None:
    if not configured():
        return
    last, more = 0.0, False
    while True:
        # One ingest across all API workers (shared limit, shared table).
        if cache.leader("mosdac-ingest", LEASE_S) and (more or time.monotonic() - last >= CYCLE_MINUTES * 60):
            def cycle():
                with SessionLocal() as db:
                    return ingest(db)
            out = await asyncio.to_thread(cycle)
            last, more = time.monotonic(), bool(out.get("more"))
            log.info("MOSDAC cycle: %s", out)
        await asyncio.sleep(60)


# --------------------------------------------------------------------------
# Reading it back
# --------------------------------------------------------------------------

def observed_days(db: Session, lat: float, lon: float, days: int = 8,
                  now: datetime | None = None) -> dict[date, dict]:
    """{IST date: {"mm", "coverage"}} for the past `days` days at this spot.
    mm = mean rate over the slots read x 24 h; coverage = slots read / 48."""
    now = now or datetime.now(timezone.utc)
    plat, plon = point_key(lat, lon)
    rows = db.execute(select(SatRain.slot, SatRain.mm_h).where(
        SatRain.dataset == MOSDAC_DATASET, SatRain.lat == plat, SatRain.lon == plon,
        SatRain.slot >= now - timedelta(days=days + 1))).all()
    by_day: dict[date, list[float]] = {}
    for slot, rate in rows:
        slot = slot if slot.tzinfo else slot.replace(tzinfo=timezone.utc)
        by_day.setdefault(slot.astimezone(IST).date(), []).append(rate)
    return {d: {"mm": round(float(np.mean(v)) * 24, 1), "coverage": round(min(1.0, len(v) / 48), 2)}
            for d, v in by_day.items()}


def last_24h(db: Session, lat: float, lon: float, now: datetime | None = None) -> dict | None:
    """Rain actually seen in the last 24 h: each image's rate x its 30 minutes,
    summed over the images read (a floor, never an extrapolation — one storm
    in six hours of images is not stretched over the whole day), plus how many
    hours of images that covers."""
    now = now or datetime.now(timezone.utc)
    plat, plon = point_key(lat, lon)
    q = select(func.sum(SatRain.mm_h), func.count(), func.max(SatRain.slot)).where(
        SatRain.dataset == MOSDAC_DATASET, SatRain.lat == plat, SatRain.lon == plon,
        SatRain.slot >= now - timedelta(hours=24))
    total, n, latest = db.execute(q).one()
    if not n:
        return None
    return {"mm": round(float(total) * 0.5, 1), "hours": n * 0.5, "coverage": round(min(1.0, n / 48), 2),
            "latest": (latest if latest.tzinfo else latest.replace(tzinfo=timezone.utc)).isoformat(),
            "source": SOURCE}


def trusted(days: dict[date, dict]) -> dict[date, float]:
    return {d: v["mm"] for d, v in days.items() if v["coverage"] >= MIN_COVERAGE}

