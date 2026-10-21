"""When this crop will actually be ready — from heat, not from the calendar.

A crop does not mature on a number of days. It matures on accumulated warmth,
which is why the same variety is cut three weeks apart in a cold year and a hot
one, and why a flat "rice is 160 days" is a guess dressed up as a number. This
predicts the harvest from the heat that has actually fallen on *this* field,
using the growing-degree-day model every agronomy department uses:

    GDD for a day = max(0, min(mean temperature, cap) - base temperature)

summed from sowing. Each crop has a base below which it does not develop and a
total it needs to reach maturity, both authored in the knowledge base. The day
that total is reached is the harvest.

Three bases, in order of how much they are worth:

  observed   the satellite saw the canopy collapse — the crop is off, or down
  thermal    computed from this field's own daily temperatures
  calendar   no weather to be had, so the crop's typical duration

Nothing here is allowed to be clever beyond its evidence. A thermal prediction
is clamped to the crop calendar's own range, so a broken temperature series
cannot announce that rice was ready in forty days, and the farmer's answer
overrides all three — they are standing in the field and we are not.

The read path never goes to the network. Predictions are served from the cache
the daily sweep warms; a farm with no cached series yet falls back to the
calendar rather than making a farmer wait on an HTTP call.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx

from app.config import WEATHER_CACHE_DIR

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY = "temperature_2m_min,temperature_2m_max"
TIMEOUT_S = 20.0

#: How long a cached season series stays fresh. A day's warmth does not change
#: once it has happened, so only the tail is ever stale.
CACHE_MAX_AGE_H = 20

#: Days after the predicted harvest before a field that nobody has spoken for
#: is treated as gone quiet. Long enough to cover a wet week and a late
#: contractor, short enough that the field does not count as growing for ever.
HARVEST_GRACE_DAYS = 21

#: Mean temperature above which a crop stops developing faster. The modified
#: GDD method caps it; without a cap a 44°C May inflates the sum and the
#: prediction arrives early.
DEFAULT_CAP_C = 35.0

CACHE_DIR = WEATHER_CACHE_DIR / "season"


@dataclass(frozen=True)
class Harvest:
    """The day this field's crop is expected off, and how much that is worth."""

    on: date
    basis: str          # 'observed' | 'thermal' | 'calendar'
    gdd: float | None = None
    gdd_target: float | None = None
    days_counted: int = 0

    @property
    def confidence(self) -> str:
        if self.basis == "observed":
            return "high"
        if self.basis == "calendar":
            return "low"
        return "high" if self.days_counted >= 30 else "medium"

    def to_json(self) -> dict:
        return {"on": self.on.isoformat(), "basis": self.basis, "confidence": self.confidence,
                "gdd": round(self.gdd) if self.gdd is not None else None,
                "gdd_target": self.gdd_target}


def _cache_path(lat: float, lon: float, start: date) -> "object":
    return CACHE_DIR / f"{lat:.2f}_{lon:.2f}_{start.isoformat()}.json"


def read_series(lat: float, lon: float, start: date) -> dict[date, float] | None:
    """Daily mean temperatures from `start`, as far as the cache has them."""
    p = _cache_path(round(lat, 2), round(lon, 2), start)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text())
        return {date.fromisoformat(k): float(v) for k, v in raw["means"].items()}
    except (ValueError, KeyError, TypeError):
        return None


def _fresh(lat: float, lon: float, start: date) -> bool:
    p = _cache_path(round(lat, 2), round(lon, 2), start)
    if not p.exists():
        return False
    try:
        at = datetime.fromisoformat(json.loads(p.read_text())["fetched_at"])
    except (ValueError, KeyError, TypeError):
        return False
    return datetime.now(UTC) - at < timedelta(hours=CACHE_MAX_AGE_H)


def fetch_series(lat: float, lon: float, start: date, *, today: date | None = None,
                 client: httpx.Client | None = None) -> dict[date, float] | None:
    """Daily mean temperatures from sowing to today, cached on disk.

    One call per field per day, and the answer is reused by every read until
    tomorrow. Open-Meteo's archive lags a few days, so the recent tail comes
    from the forecast endpoint's past days; a gap in the middle is simply a day
    that contributes nothing, which is honest — we never invent warmth.
    """
    lat, lon = round(lat, 2), round(lon, 2)
    today = today or date.today()
    if _fresh(lat, lon, start):
        return read_series(lat, lon, start)

    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S)
    means: dict[date, float] = {}
    try:
        for url, params in (
            (ARCHIVE_URL, {"start_date": start.isoformat(), "end_date": today.isoformat()}),
            (FORECAST_URL, {"past_days": 92, "forecast_days": 1}),
        ):
            try:
                r = client.get(url, params={"latitude": lat, "longitude": lon, "daily": DAILY,
                                            "timezone": "Asia/Kolkata", **params})
                payload = r.json()
                if r.status_code != 200 or payload.get("error"):
                    continue
                d = payload["daily"]
                for on, lo, hi in zip(d["time"], d["temperature_2m_min"], d["temperature_2m_max"], strict=False):
                    if lo is None or hi is None:
                        continue
                    day = date.fromisoformat(on)
                    if start <= day <= today:
                        means[day] = (lo + hi) / 2
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                continue
    finally:
        if own:
            client.close()

    if not means:
        return read_series(lat, lon, start)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(lat, lon, start).write_text(json.dumps({
        "fetched_at": datetime.now(UTC).isoformat(),
        "means": {d.isoformat(): round(v, 2) for d, v in sorted(means.items())},
    }))
    return means


def gdd(means: dict[date, float], base: float, cap: float = DEFAULT_CAP_C) -> float:
    """Accumulated growing degree days over the series."""
    return sum(max(0.0, min(t, cap) - base) for t in means.values())


def _senesced(ndvi: list[dict], sown: date) -> date | None:
    """The day the canopy collapsed, if the satellite watched it happen.

    A standing crop holds a high NDVI and then falls away as it ripens; a cut
    field falls off a cliff. A sustained drop to below 55% of this season's
    peak, with the peak itself high enough to have been a real canopy, is the
    closest thing to watching the harvest.
    """
    rows = sorted((r for r in ndvi if r.get("on") and r.get("mean") is not None), key=lambda r: r["on"])
    rows = [r for r in rows if r["on"] >= sown]
    if len(rows) < 4:
        return None
    peak = max(r["mean"] for r in rows)
    if peak < 0.45:
        return None
    for i, r in enumerate(rows[:-1]):
        if r["mean"] < peak * 0.55 and rows[i + 1]["mean"] < peak * 0.55:
            return r["on"]
    return None


def predict(kb, farm, *, today: date | None = None, allow_fetch: bool = False,
            ndvi: list[dict] | None = None) -> Harvest:
    """When this field's crop is expected off.

    `allow_fetch` is false everywhere a farmer is waiting on a response: the
    prediction is served from what the sweep has already cached, and a field
    with nothing cached gets the calendar answer rather than a slow one.
    """
    today = today or date.today()
    crop = kb.crops[farm.crop]
    sown = kb.sown_on(farm.crop, farm.sowing_date, farm.date_basis, getattr(farm, "state", None))

    # The crop calendar's own bounds. A thermal prediction is clamped to these,
    # because a temperature series with a hole in it should move the estimate,
    # not replace the agronomy.
    earliest = sown + timedelta(days=crop["stages"][-1]["das"][0])
    latest = sown + timedelta(days=int(crop["season_ends_das"]))
    calendar = Harvest(on=latest, basis="calendar")

    # What the satellite already saw beats anything computed. The sweep stores
    # it on the field so a read never has to go looking.
    seen = getattr(farm, "harvest_seen_on", None)
    if seen is None and ndvi:
        seen = _senesced(ndvi, sown)
    if seen and seen >= earliest:
        return Harvest(on=seen, basis="observed")

    target = crop.get("gdd_to_harvest")
    base = crop.get("gdd_base")
    if target is None or base is None:
        return calendar

    means = (fetch_series(farm.lat, farm.lon, sown, today=today) if allow_fetch
             else read_series(farm.lat, farm.lon, sown))
    if not means:
        return calendar

    cap = float(crop.get("gdd_cap", DEFAULT_CAP_C))
    so_far = gdd(means, float(base), cap)
    counted = len(means)

    if so_far >= target:
        # Already there: find the day the total was reached.
        run = 0.0
        for on in sorted(means):
            run += max(0.0, min(means[on], cap) - float(base))
            if run >= target:
                return Harvest(on=_clamp(on, earliest, latest), basis="thermal",
                               gdd=so_far, gdd_target=target, days_counted=counted)

    # Not yet: carry on at the rate this field has been warming lately.
    recent = [means[d] for d in sorted(means)[-14:]]
    rate = sum(max(0.0, min(t, cap) - float(base)) for t in recent) / len(recent) if recent else 0.0
    if rate <= 0:
        return calendar
    ahead = math.ceil((target - so_far) / rate)
    return Harvest(on=_clamp(today + timedelta(days=ahead), earliest, latest), basis="thermal",
                   gdd=so_far, gdd_target=target, days_counted=counted)


def _clamp(on: date, earliest: date, latest: date) -> date:
    return max(earliest, min(on, latest))
