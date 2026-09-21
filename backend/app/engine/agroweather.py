"""Hour-by-hour agro-weather for a point: what the farmer's alerts are made of.

Source chain (first that answers wins; the bundle always says which):
  1. Open-Meteo forecast — 7 past + 7 coming days, hourly and daily: temperature,
     humidity, dew point, feels-like, rain and its probability, cloud,
     visibility, wind, gusts and direction, UV, pressure, FAO-56 ET0 and the
     soil layers. Current conditions are then overlaid with OpenWeather's
     observed values when the key works.
  2. OpenWeather current + 5-day / 3-hour forecast (no past days, no soil, no
     UV); ET0 from FAO-56 Hargreaves on the daily min/max.
  3. The last bundle for this location, however old, flagged stale.
Everything is cached on disk per location for CACHE_MINUTES, so a district of
farms sharing a grid cell costs one call, and the keyless Open-Meteo tier's
per-IP limit is not burnt by page loads. Times are local (IST), naive.
"""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app import cache

log = logging.getLogger("annrakshak.agroweather")
from app.config import (
    AGRO_CACHE_MINUTES,
    OPEN_METEO_URL,
    OPENWEATHER_API_KEY,
    WEATHER_CACHE_DIR,
    WEATHER_TIMEOUT_S,
)

IST = ZoneInfo("Asia/Kolkata")
OWM_NOW = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"
BATCH = 10  # Open-Meteo accepts comma-separated coordinates; keep URLs short

HOURLY = {
    "temperature_2m": "temp", "relative_humidity_2m": "rh", "dew_point_2m": "dew",
    "apparent_temperature": "feels", "precipitation": "precip", "precipitation_probability": "prob",
    "weather_code": "code", "cloud_cover": "cloud", "visibility": "vis", "wind_speed_10m": "wind",
    "wind_gusts_10m": "gust", "wind_direction_10m": "wdir", "uv_index": "uv",
    "et0_fao_evapotranspiration": "et0", "pressure_msl": "pressure", "is_day": "is_day",
    "soil_temperature_0cm": "soil_t0", "soil_temperature_6cm": "soil_t6",
    "soil_moisture_0_to_1cm": "sm0", "soil_moisture_1_to_3cm": "sm1",
    "soil_moisture_3_to_9cm": "sm3", "soil_moisture_9_to_27cm": "sm9",
}
DAILY = {
    "weather_code": "code", "temperature_2m_max": "tmax", "temperature_2m_min": "tmin",
    "apparent_temperature_max": "feels_max", "precipitation_sum": "rain",
    "precipitation_probability_max": "prob", "precipitation_hours": "rain_hours",
    "wind_speed_10m_max": "wind_max", "wind_gusts_10m_max": "gust_max",
    "wind_direction_10m_dominant": "wdir", "uv_index_max": "uv_max", "sunshine_duration": "sunshine_s",
    "shortwave_radiation_sum": "radiation", "et0_fao_evapotranspiration": "et0",
    "sunrise": "sunrise", "sunset": "sunset",
}
CURRENT = {k: v for k, v in HOURLY.items() if not k.startswith(("soil", "et0", "precipitation_prob", "dew"))}

_mem: dict[tuple[float, float], tuple[float, dict]] = {}


class AgroWeatherUnavailable(RuntimeError):
    pass


def now_ist() -> datetime:
    return datetime.now(IST).replace(tzinfo=None, second=0, microsecond=0)


def _key(lat: float, lon: float) -> tuple[float, float]:
    return round(lat, 2), round(lon, 2)


def _file(k: tuple[float, float]):
    return WEATHER_CACHE_DIR / f"agro_{k[0]:.2f}_{k[1]:.2f}.json"


def _fresh(b: dict) -> bool:
    return time.time() - b.get("_ts", 0) < AGRO_CACHE_MINUTES * 60


SHARED_TTL_S = 12 * 3600


def _store(k, b: dict) -> None:
    b["_ts"] = time.time()
    _mem[k] = (b["_ts"], b)
    cache.set_json(f"agro:{k[0]:.2f}_{k[1]:.2f}", b, SHARED_TTL_S)  # other instances reuse it
    WEATHER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _file(k).write_text(json.dumps(b))


def _cached(k) -> dict | None:
    if k in _mem and _fresh(_mem[k][1]):
        return _mem[k][1]
    shared = cache.get_json(f"agro:{k[0]:.2f}_{k[1]:.2f}")
    if shared and (k not in _mem or shared.get("_ts", 0) > _mem[k][0]):
        _mem[k] = (shared.get("_ts", 0), shared)
        return shared
    if k in _mem:
        return _mem[k][1]
    f = _file(k)
    if f.exists():
        try:
            b = json.loads(f.read_text())
            _mem[k] = (b.get("_ts", 0), b)
            return b
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------
# Open-Meteo
# --------------------------------------------------------------------------

def _om_params(lats: list[float], lons: list[float]) -> dict:
    return {
        "latitude": ",".join(f"{x:.2f}" for x in lats), "longitude": ",".join(f"{x:.2f}" for x in lons),
        "timezone": "Asia/Kolkata", "past_days": 7, "forecast_days": 7,
        "hourly": ",".join(HOURLY), "daily": ",".join(DAILY), "current": ",".join(CURRENT),
    }


def _columns(block: dict, names: dict, time_key: str) -> list[dict]:
    times = block.get("time") or []
    out = []
    for i, t in enumerate(times):
        row = {time_key: t}
        for src, dst in names.items():
            col = block.get(src)
            row[dst] = col[i] if col is not None and i < len(col) else None
        out.append(row)
    return out


def parse_open_meteo(p: dict, lat: float, lon: float) -> dict:
    hours = _columns(p.get("hourly") or {}, HOURLY, "t")
    days = _columns(p.get("daily") or {}, DAILY, "on")
    cur = p.get("current") or {}
    current = {dst: cur.get(src) for src, dst in CURRENT.items()} | {"time": cur.get("time")}
    if not hours or not days:
        raise ValueError("Open-Meteo payload without hourly/daily data")
    has_soil = any(h.get("sm0") is not None for h in hours)
    return {
        "lat": lat, "lon": lon, "fetched_at": now_ist().isoformat(), "stale": False,
        "current": current, "hours": hours, "days": days,
        "source": {"forecast": "Open-Meteo", "current": "Open-Meteo (modelled)",
                   "soil": "Open-Meteo soil model (estimate)" if has_soil else None,
                   "et0": "Open-Meteo (FAO-56 Penman-Monteith)"},
    }


def _fetch_open_meteo(points: list[tuple[float, float]], client: httpx.Client) -> list[dict]:
    r = client.get(OPEN_METEO_URL, params=_om_params([p[0] for p in points], [p[1] for p in points]))
    data = r.json()
    if r.status_code != 200 or (isinstance(data, dict) and data.get("error")):
        raise ValueError(f"Open-Meteo: {r.status_code} {str(data)[:120]}")
    payloads = data if isinstance(data, list) else [data]
    return [parse_open_meteo(pl, lat, lon) for pl, (lat, lon) in zip(payloads, points)]


# --------------------------------------------------------------------------
# OpenWeather (observed now; forecast fallback)
# --------------------------------------------------------------------------

def owm_code(cid: int | None) -> int | None:
    """OpenWeather condition id -> the nearest WMO code, so the rules speak one language."""
    if cid is None:
        return None
    if 200 <= cid < 300:
        return 95
    if 300 <= cid < 400:
        return 53
    if cid == 511:
        return 66
    if 520 <= cid < 600:
        return 81
    if 500 <= cid < 600:
        return 63 if cid < 502 else 65
    if 600 <= cid < 700:
        return 71
    if 700 <= cid < 800:
        return 45
    return {800: 0, 801: 1, 802: 2}.get(cid, 3)


def _local(ts: int) -> str:
    return datetime.fromtimestamp(ts, IST).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M")


def parse_owm_now(j: dict) -> dict:
    w = j.get("wind") or {}
    m = j.get("main") or {}
    return {
        "temp": m.get("temp"), "feels": m.get("feels_like"), "rh": m.get("humidity"),
        "pressure": m.get("sea_level") or m.get("pressure"),
        "wind": round(w["speed"] * 3.6, 1) if w.get("speed") is not None else None,
        "gust": round(w["gust"] * 3.6, 1) if w.get("gust") is not None else None,
        "wdir": w.get("deg"), "vis": j.get("visibility"), "cloud": (j.get("clouds") or {}).get("all"),
        "precip": (j.get("rain") or {}).get("1h", 0.0),
        "code": owm_code((j.get("weather") or [{}])[0].get("id")),
        "time": _local(j["dt"]) if j.get("dt") else None,
        "station": j.get("name") or None,
    }


def parse_owm_forecast(j: dict, lat: float) -> tuple[list[dict], list[dict]]:
    """3-hour slots -> hourly rows (each slot spread over its 3 hours) and daily rows."""
    hours: list[dict] = []
    for s in j.get("list") or []:
        m, w = s.get("main") or {}, s.get("wind") or {}
        # 'rain.3h' is the 3 hours ending at dt: spread it over dt-2h, dt-1h, dt
        start = datetime.fromtimestamp(s["dt"], IST).replace(tzinfo=None) - timedelta(hours=2)
        rain3 = (s.get("rain") or {}).get("3h", 0.0)
        pod = (s.get("sys") or {}).get("pod")
        for k in range(3):
            t = start + timedelta(hours=k)
            hours.append({
                "t": t.strftime("%Y-%m-%dT%H:%M"), "temp": m.get("temp"), "rh": m.get("humidity"),
                "dew": m.get("dew_point"), "feels": m.get("feels_like"), "precip": round(rain3 / 3, 2),
                "prob": round((s.get("pop") or 0) * 100), "code": owm_code((s.get("weather") or [{}])[0].get("id")),
                "cloud": (s.get("clouds") or {}).get("all"), "vis": s.get("visibility"),
                "wind": round(w["speed"] * 3.6, 1) if w.get("speed") is not None else None,
                "gust": round(w["gust"] * 3.6, 1) if w.get("gust") is not None else None,
                "wdir": w.get("deg"), "uv": None, "et0": None,
                "pressure": m.get("sea_level") or m.get("pressure"),
                "is_day": 1 if (pod == "d" or 6 <= t.hour < 18) else 0,
            })
    days: list[dict] = []
    by_day: dict[str, list[dict]] = {}
    for h in hours:
        by_day.setdefault(h["t"][:10], []).append(h)
    for on, hs in sorted(by_day.items()):
        temps = [h["temp"] for h in hs if h["temp"] is not None]
        if not temps:
            continue
        tmin, tmax = min(temps), max(temps)
        windiest = max(hs, key=lambda h: h["wind"] or 0)
        d = date.fromisoformat(on)
        days.append({
            "on": on, "tmin": tmin, "tmax": tmax,
            "feels_max": max((h["feels"] for h in hs if h["feels"] is not None), default=None),
            "rain": round(sum(h["precip"] or 0 for h in hs), 1), "prob": max(h["prob"] or 0 for h in hs),
            "rain_hours": sum(1 for h in hs if (h["precip"] or 0) >= 0.1),
            "wind_max": windiest["wind"], "gust_max": max((h["gust"] or 0 for h in hs), default=None),
            "wdir": windiest["wdir"], "uv_max": None, "sunshine_s": None, "radiation": None,
            "code": max((h["code"] or 0 for h in hs), default=None),
            "et0": round(hargreaves_et0(tmin, tmax, lat, d.timetuple().tm_yday), 2),
            "sunrise": None, "sunset": None,
        })
    return hours, days


def _fetch_owm(lat: float, lon: float, client: httpx.Client) -> dict:
    params = {"lat": lat, "lon": lon, "units": "metric", "appid": OPENWEATHER_API_KEY}
    r = client.get(OWM_FORECAST, params=params)
    r.raise_for_status()
    hours, days = parse_owm_forecast(r.json(), lat)
    now = _owm_now(lat, lon, client) or {}
    return {
        "lat": lat, "lon": lon, "fetched_at": now_ist().isoformat(), "stale": False,
        "current": now, "hours": hours, "days": days,
        "source": {"forecast": "OpenWeather 5-day / 3-hour", "current": "OpenWeather (observed)" if now else None,
                   "soil": None, "et0": "Hargreaves (FAO-56 eq. 52) from min/max temperature"},
    }


def _owm_now(lat: float, lon: float, client: httpx.Client) -> dict | None:
    if not OPENWEATHER_API_KEY:
        return None
    try:
        r = client.get(OWM_NOW, params={"lat": lat, "lon": lon, "units": "metric", "appid": OPENWEATHER_API_KEY})
        return parse_owm_now(r.json()) if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def overlay_observed(b: dict, obs: dict | None) -> dict:
    """Observed values replace the modelled current conditions; UV and day/night
    (which OpenWeather's free tier lacks) stay from the model."""
    if not obs:
        return b
    cur = dict(b["current"])
    for k, v in obs.items():
        if v is not None:
            cur[k] = v
    b["current"] = cur
    b["source"] = b["source"] | {"current": "OpenWeather (observed) · UV: Open-Meteo"}
    return b


# --------------------------------------------------------------------------
# FAO-56 Hargreaves (fallback ET0)
# --------------------------------------------------------------------------

def extraterrestrial_radiation(lat: float, doy: int) -> float:
    """Ra, MJ m-2 day-1 (FAO-56 eq. 21)."""
    phi = math.radians(lat)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    delta = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    return 24 * 60 / math.pi * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws))


def hargreaves_et0(tmin: float, tmax: float, lat: float, doy: int) -> float:
    """Reference evapotranspiration, mm/day (FAO-56 eq. 52)."""
    ra = extraterrestrial_radiation(lat, doy)
    return max(0.0, 0.0023 * ((tmax + tmin) / 2 + 17.8) * math.sqrt(max(tmax - tmin, 0.0)) * 0.408 * ra)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def prefetch(points: list[tuple[float, float]], *, client: httpx.Client | None = None) -> int:
    """Warm the cache for many farms in a few Open-Meteo calls. Returns how many
    locations were fetched. Failures are silent: bundle() falls back per point."""
    todo = sorted({_key(*p) for p in points if not ((b := _cached(_key(*p))) and _fresh(b))})
    if not todo:
        return 0
    own = client is None
    client = client or httpx.Client(timeout=WEATHER_TIMEOUT_S * 2)
    done = 0
    try:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            try:
                for k, b in zip(chunk, _fetch_open_meteo(chunk, client)):
                    _store(k, overlay_observed(b, _owm_now(k[0], k[1], client)))
                    done += 1
            except (httpx.HTTPError, ValueError, KeyError):
                break  # rate-limited or down: the per-point path takes over
    finally:
        if own:
            client.close()
    return done


def bundle(lat: float, lon: float, *, client: httpx.Client | None = None) -> dict:
    """The farm's agro-weather, with past days' rain replaced by what the
    INSAT-3DS satellite observed there wherever enough of the day was covered."""
    return with_observed_rain(_bundle(lat, lon, client=client), lat, lon)


def with_observed_rain(b: dict, lat: float, lon: float) -> dict:
    from app import mosdac  # imported late: it needs the database
    from app.db import SessionLocal

    try:
        with SessionLocal() as db:
            days = mosdac.observed_days(db, lat, lon)
            last = mosdac.last_24h(db, lat, lon)
    except Exception as e:  # noqa: BLE001 — the weather must never fail over this
        log.warning("satellite rain unavailable: %s", e)
        return b
    trusted = {d.isoformat(): mm for d, mm in mosdac.trusted(days).items()}
    today = now_ist().date().isoformat()
    if not trusted and not last:
        return b
    out = dict(b)  # the cached bundle is shared: copy, never edit it
    out["days"] = [d | {"rain": trusted[d["on"]], "rain_src": "satellite"}
                   if d["on"] in trusted and d["on"] < today else d for d in b["days"]]
    out["sat_rain"] = last
    return out


def _bundle(lat: float, lon: float, *, client: httpx.Client | None = None) -> dict:
    k = _key(lat, lon)
    cached = _cached(k)
    if cached and _fresh(cached):
        return cached
    own = client is None
    client = client or httpx.Client(timeout=WEATHER_TIMEOUT_S)
    try:
        try:
            b = _fetch_open_meteo([k], client)[0]
            b = overlay_observed(b, _owm_now(k[0], k[1], client))
            _store(k, b)
            return b
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            pass
        if OPENWEATHER_API_KEY:
            try:
                b = _fetch_owm(k[0], k[1], client)
                if b["hours"]:
                    _store(k, b)
                    return b
            except (httpx.HTTPError, ValueError, KeyError):
                pass
    finally:
        if own:
            client.close()
    if cached:
        return cached | {"stale": True}
    raise AgroWeatherUnavailable(f"no agro-weather for {k}: Open-Meteo, OpenWeather and cache all failed")
