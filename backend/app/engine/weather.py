"""Daily weather window for a location: the trailing week plus the forecast.

Source chain, first that answers wins, and the answer always says which:
  1. Open-Meteo forecast (past 7 days + next 7)         source="live"
  2. Open-Meteo archive (last 14 days, no forecast)      source="archive"
  3. last cached window for this location, any age      source="cache"
An outage raises WeatherUnavailable rather than returning an empty window: an
empty window scores as "not favourable" everywhere, which would silently turn
a failed API call into a calm day.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta

import httpx

from app.config import (
    OPEN_METEO_URL,
    WEATHER_CACHE_DIR,
    WEATHER_CACHE_MAX_AGE_H,
    WEATHER_FORECAST_DAYS,
    WEATHER_PAST_DAYS,
    WEATHER_TIMEOUT_S,
)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = "temperature_2m_max,temperature_2m_min,relative_humidity_2m_max,precipitation_sum"


class WeatherUnavailable(RuntimeError):
    pass


@dataclass
class Day:
    on: date
    rh_max: float | None
    t_min: float | None
    t_max: float | None
    rain_mm: float | None
    from_sensor: bool = False

    @property
    def t_mean(self) -> float | None:
        if self.t_min is None or self.t_max is None:
            return None
        return (self.t_min + self.t_max) / 2


@dataclass
class Window:
    days: list[Day]
    source: str
    fetched_at: datetime

    def to_json(self) -> dict:
        return {
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat(),
            "days": [{**asdict(d), "on": d.on.isoformat()} for d in self.days],
        }

    @classmethod
    def from_json(cls, data: dict, source: str | None = None) -> Window:
        days = [Day(**{**d, "on": date.fromisoformat(d["on"])}) for d in data["days"]]
        return cls(days, source or data["source"], datetime.fromisoformat(data["fetched_at"]))


def _parse(payload: dict) -> list[Day]:
    d = payload["daily"]
    return [
        Day(date.fromisoformat(t), rh, tmin, tmax, rain)
        for t, tmax, tmin, rh, rain in zip(
            d["time"],
            d["temperature_2m_max"],
            d["temperature_2m_min"],
            d["relative_humidity_2m_max"],
            d["precipitation_sum"],
        )
    ]


def _cache_path(lat: float, lon: float):
    return WEATHER_CACHE_DIR / f"{lat:.2f}_{lon:.2f}.json"


def _read_cache(lat: float, lon: float) -> Window | None:
    p = _cache_path(lat, lon)
    if not p.exists():
        return None
    try:
        return Window.from_json(json.loads(p.read_text()))
    except (ValueError, KeyError):
        return None


def _write_cache(lat: float, lon: float, w: Window) -> None:
    WEATHER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(lat, lon).write_text(json.dumps(w.to_json()))


def fetch_window(lat: float, lon: float, *, client: httpx.Client | None = None) -> Window:
    lat, lon = round(lat, 2), round(lon, 2)
    cached = _read_cache(lat, lon)
    now = datetime.now(UTC)
    if cached and now - cached.fetched_at < timedelta(hours=WEATHER_CACHE_MAX_AGE_H):
        return cached

    own = client is None
    client = client or httpx.Client(timeout=WEATHER_TIMEOUT_S)
    try:
        attempts = [
            (
                "live",
                OPEN_METEO_URL,
                {"past_days": WEATHER_PAST_DAYS, "forecast_days": WEATHER_FORECAST_DAYS},
            ),
            (
                "archive",
                ARCHIVE_URL,
                {
                    "start_date": (date.today() - timedelta(days=13)).isoformat(),
                    "end_date": date.today().isoformat(),
                },
            ),
        ]
        for source, url, extra in attempts:
            try:
                r = client.get(
                    url,
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "daily": DAILY,
                        "timezone": "Asia/Kolkata",
                        **extra,
                    },
                )
                payload = r.json()
                if r.status_code != 200 or payload.get("error"):
                    continue
                days = [d for d in _parse(payload) if d.rh_max is not None]
                if not days:
                    continue
                w = Window(days, source, now)
                _write_cache(lat, lon, w)
                return w
            except (httpx.HTTPError, ValueError, KeyError):
                continue
    finally:
        if own:
            client.close()

    if cached:
        return Window(cached.days, "cache", cached.fetched_at)
    raise WeatherUnavailable(f"no weather for {lat},{lon}: live, archive and cache all failed")


def fetch_month_rain(lat: float, lon: float, *, client: httpx.Client | None = None) -> dict | None:
    """Rain from the 1st of this month to today (archive API), cached like the
    window. Returns None rather than a guess when nothing answers."""
    lat, lon = round(lat, 2), round(lon, 2)
    today = date.today()
    p = WEATHER_CACHE_DIR / f"month_{lat:.2f}_{lon:.2f}.json"
    now = datetime.now(UTC)
    cached = None
    if p.exists():
        try:
            cached = json.loads(p.read_text())
        except ValueError:
            cached = None
    if cached and cached["month"] == today.strftime("%Y-%m") and \
            now - datetime.fromisoformat(cached["fetched_at"]) < timedelta(hours=WEATHER_CACHE_MAX_AGE_H):
        return cached
    own = client is None
    client = client or httpx.Client(timeout=WEATHER_TIMEOUT_S)
    try:
        r = client.get(ARCHIVE_URL, params={
            "latitude": lat, "longitude": lon, "daily": "precipitation_sum", "timezone": "Asia/Kolkata",
            "start_date": today.replace(day=1).isoformat(), "end_date": today.isoformat(),
        })
        payload = r.json()
        vals = [v for v in payload["daily"]["precipitation_sum"] if v is not None]
        if r.status_code != 200 or not vals:
            raise ValueError("no data")
        out = {"month": today.strftime("%Y-%m"), "rain_mm": round(sum(vals), 1), "days": len(vals),
               "fetched_at": now.isoformat(), "source": "archive"}
        WEATHER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out))
        return out
    except (httpx.HTTPError, ValueError, KeyError):
        if cached and cached["month"] == today.strftime("%Y-%m"):
            return cached | {"source": "cache"}
        return None
    finally:
        if own:
            client.close()


def merge_rain(window: Window, observed: dict[date, float]) -> Window:
    """Past days' rain as the satellite observed it (app.mosdac), in place of the
    model's estimate. Only rain: temperature and humidity stay as they were."""
    if not observed:
        return window
    days = [Day(d.on, d.rh_max, d.t_min, d.t_max, observed[d.on], d.from_sensor)
            if d.on in observed and not d.from_sensor else d for d in window.days]
    return Window(days, window.source, window.fetched_at)


def merge_sensor(window: Window, readings: list[dict]) -> Window:
    """In-field sensor days replace the regional value for that day."""
    by_day = {r["on"]: r for r in readings}
    days = []
    for d in window.days:
        s = by_day.pop(d.on, None)
        if s:
            days.append(
                Day(
                    d.on,
                    s.get("rh_max", d.rh_max) if s.get("rh_max") is not None else d.rh_max,
                    s.get("t_min") if s.get("t_min") is not None else d.t_min,
                    s.get("t_max") if s.get("t_max") is not None else d.t_max,
                    s.get("rain_mm") if s.get("rain_mm") is not None else d.rain_mm,
                    from_sensor=True,
                )
            )
        else:
            days.append(d)
    for on, s in sorted(by_day.items()):
        days.append(Day(on, s.get("rh_max"), s.get("t_min"), s.get("t_max"), s.get("rain_mm"), True))
    days.sort(key=lambda d: d.on)
    return Window(days, window.source, window.fetched_at)
