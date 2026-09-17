"""Conditions at the farm right now: current weather, modelled soil moisture and
temperature, and soil chemistry from the ISRIC SoilGrids map.

Every value says where it came from, and whether it was measured or estimated.
A soil-map pH is an estimate for a 250 m cell, not a measurement of this field
— the app must say so. Measured values (a field sensor, the farmer's Soil
Health Card) are preferred by the caller when present.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import httpx

from app.config import DATA_DIR, OPENWEATHER_API_KEY
from app.kb import tr

OWM_URL = "https://api.openweathermap.org/data/2.5/weather"
OM_URL = "https://api.open-meteo.com/v1/forecast"
SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
SOILGRIDS_WCS = "https://maps.isric.org/mapserv"  # same maps via OGC WCS; up when the REST API is paused
NOW_TTL = 600            # s — current weather is cached 10 minutes per location
SOIL_FAIL_TTL = 3600     # s — after a SoilGrids timeout, don't try again for an hour
SOIL_CACHE = DATA_DIR / "soil_cache"

_now_cache: dict[tuple, tuple[float, dict]] = {}

# WMO weather codes (Open-Meteo) grouped into plain words.
WMO = [
    ((0,), {"en": "clear sky", "hi": "साफ़ आसमान", "mr": "निरभ्र आकाश"}),
    ((1, 2), {"en": "partly cloudy", "hi": "आंशिक बादल", "mr": "अंशतः ढगाळ"}),
    ((3,), {"en": "overcast", "hi": "घने बादल", "mr": "पूर्ण ढगाळ"}),
    ((45, 48), {"en": "fog", "hi": "कोहरा", "mr": "धुके"}),
    ((51, 53, 55, 56, 57), {"en": "drizzle", "hi": "बूँदाबाँदी", "mr": "रिमझिम"}),
    ((61, 63, 65, 66, 67, 80, 81, 82), {"en": "rain", "hi": "बारिश", "mr": "पाऊस"}),
    ((95, 96, 99), {"en": "thunderstorm", "hi": "आँधी-तूफ़ान", "mr": "वादळी पाऊस"}),
]


def _wmo_text(code: int | None, lang: str) -> str | None:
    if code is None:
        return None
    for codes, text in WMO:
        if code in codes:
            return tr(text, lang)
    return None


def owm_to_wmo(cid: int | None) -> int | None:
    """OpenWeather condition id -> the nearest WMO weather code."""
    if cid is None:
        return None
    return (95 if 200 <= cid < 300 else 53 if 300 <= cid < 400 else 63 if 500 <= cid < 700
            else 45 if 700 <= cid < 800 else 0 if cid == 800 else 2 if cid in (801, 802) else 3)


def _owm_text(cid: int | None, lang: str, fallback: str | None) -> str | None:
    """OpenWeather condition id -> our wording. OWM translates Hindi but not
    Marathi, so both Indian languages use our own words for consistency."""
    if lang == "en" or cid is None:
        return fallback
    return _wmo_text(owm_to_wmo(cid), lang) or fallback


def weather_text(weather: dict, lang: str) -> str | None:
    """The sky in words, in any language, from a stored reading ('wmo' code)."""
    return _wmo_text(weather.get("wmo"), lang) or weather.get("text")


def _open_meteo(lat: float, lon: float, client: httpx.Client) -> dict:
    r = client.get(OM_URL, params={
        "latitude": lat, "longitude": lon, "timezone": "Asia/Kolkata", "forecast_days": 1,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
        "hourly": "soil_moisture_0_to_1cm,soil_moisture_3_to_9cm,soil_temperature_0cm",
    })
    r.raise_for_status()
    return r.json()


def _hour_value(payload: dict, key: str):
    hourly = payload.get("hourly") or {}
    times, vals = hourly.get("time") or [], hourly.get(key) or []
    now = datetime.now().strftime("%Y-%m-%dT%H:00")
    for t, v in zip(times, vals):
        if t == now:
            return v
    return vals[datetime.now().hour] if len(vals) > datetime.now().hour else None


def conditions_now(lat: float, lon: float, lang: str, *, client: httpx.Client | None = None) -> dict:
    """{'weather': {...} | None, 'soil_model': {...} | None} — never raises."""
    key = (round(lat, 2), round(lon, 2), lang)
    hit = _now_cache.get(key)
    if hit and time.time() - hit[0] < NOW_TTL:
        return hit[1]
    own = client is None
    client = client or httpx.Client(timeout=8.0)
    weather, soil_model, om = None, None, None
    try:
        try:
            om = _open_meteo(lat, lon, client)
        except (httpx.HTTPError, ValueError):
            om = None
        if OPENWEATHER_API_KEY:
            try:
                r = client.get(OWM_URL, params={"lat": lat, "lon": lon, "units": "metric",
                                                "lang": lang, "appid": OPENWEATHER_API_KEY})
                if r.status_code == 200:
                    j = r.json()
                    weather = {
                        "temp_c": j["main"]["temp"], "rh_pct": j["main"]["humidity"],
                        "rain_mm_1h": (j.get("rain") or {}).get("1h", 0.0),
                        "wind_kmh": round(j["wind"]["speed"] * 3.6, 1),
                        "text": _owm_text((j.get("weather") or [{}])[0].get("id"), lang,
                                          (j.get("weather") or [{}])[0].get("description")),
                        "wmo": owm_to_wmo((j.get("weather") or [{}])[0].get("id")),
                        "station": j.get("name") or None,
                        "source": "OpenWeather (current)", "observed_at": datetime.fromtimestamp(j["dt"]).isoformat(),
                    }
            except (httpx.HTTPError, KeyError, ValueError):
                weather = None
        if weather is None and om and om.get("current"):
            c = om["current"]
            weather = {
                "temp_c": c.get("temperature_2m"), "rh_pct": c.get("relative_humidity_2m"),
                "rain_mm_1h": c.get("precipitation"), "wind_kmh": c.get("wind_speed_10m"),
                "text": _wmo_text(c.get("weather_code"), lang), "wmo": c.get("weather_code"), "station": None,
                "source": "Open-Meteo (current, modelled)", "observed_at": c.get("time"),
            }
        if om:
            sm = _hour_value(om, "soil_moisture_0_to_1cm")
            sm_deep = _hour_value(om, "soil_moisture_3_to_9cm")
            st = _hour_value(om, "soil_temperature_0cm")
            if sm is not None or st is not None:
                soil_model = {
                    "moisture_pct_surface": round(sm * 100, 1) if sm is not None else None,
                    "moisture_pct_3_9cm": round(sm_deep * 100, 1) if sm_deep is not None else None,
                    "temp_c_surface": st, "source": "Open-Meteo soil model (estimate, not a measurement)",
                }
    finally:
        if own:
            client.close()
    out = {"weather": weather, "soil_model": soil_model}
    if weather:
        _now_cache[key] = (time.time(), out)
    return out


def _soil_file(lat: float, lon: float):
    return SOIL_CACHE / f"{lat:.2f}_{lon:.2f}.json"


def soilgrids(lat: float, lon: float, *, timeout: float = 6.0, client: httpx.Client | None = None) -> dict | None:
    """Topsoil (0-5 cm) pH, organic carbon, clay and nitrogen for the 250 m cell.
    Cached on disk for good (soil maps don't change); a failure is remembered
    for an hour so a slow ISRIC server can't stall a live session."""
    f = _soil_file(lat, lon)
    if f.exists():
        d = json.loads(f.read_text())
        if d.get("ok"):
            return d["value"]
        if time.time() - d.get("failed_at", 0) < SOIL_FAIL_TTL:
            return None
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        r = client.get(SOILGRIDS_URL, params=[("lon", lon), ("lat", lat), ("property", "phh2o"),
                                              ("property", "soc"), ("property", "clay"),
                                              ("property", "nitrogen"), ("depth", "0-5cm"), ("value", "mean")])
        r.raise_for_status()
        layers = {x["name"]: x for x in r.json()["properties"]["layers"]}

        def val(name):
            lay = layers.get(name)
            if not lay:
                return None
            v = lay["depths"][0]["values"].get("mean")
            return None if v is None else v / lay["unit_measure"]["d_factor"]

        value = {"ph": val("phh2o"), "soc_g_per_kg": val("soc"), "clay_pct": (val("clay") or 0) / 10 or None,
                 "nitrogen_g_per_kg": val("nitrogen"),
                 "source": "ISRIC SoilGrids 2.0 (250 m map estimate, 0-5 cm)"}
        if value["ph"] is None:
            raise ValueError("no pH in response")
        SOIL_CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"ok": True, "value": value}))
        return value
    except (httpx.HTTPError, KeyError, ValueError, IndexError):
        value = _soilgrids_wcs(lat, lon, client)
        SOIL_CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"ok": True, "value": value} if value else {"ok": False, "failed_at": time.time()}))
        return value
    finally:
        if own:
            client.close()


def _wcs_cell(prop: str, lat: float, lon: float, client: httpx.Client) -> float | None:
    """Median of the valid 250 m cells in a ~2 km window, from the WCS GeoTIFF
    (int values, scaled by 10 for pH, 0 = no data)."""
    import io  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    for d in (0.01, 0.03):  # widen once: towns and water bodies are masked out of the map
        r = client.get(SOILGRIDS_WCS, params=[
            ("map", f"/map/{prop}.map"), ("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"),
            ("COVERAGEID", f"{prop}_0-5cm_mean"), ("FORMAT", "image/tiff"),
            ("SUBSET", f"long({lon - d},{lon + d})"), ("SUBSET", f"lat({lat - d},{lat + d})"),
            ("SUBSETTINGCRS", "http://www.opengis.net/def/crs/EPSG/0/4326"),
            ("OUTPUTCRS", "http://www.opengis.net/def/crs/EPSG/0/4326"),
        ])
        r.raise_for_status()
        if "tiff" not in r.headers.get("content-type", ""):
            return None
        a = np.array(Image.open(io.BytesIO(r.content)))
        valid = a[a > 0]
        if valid.size:
            return float(np.median(valid))
    return None


def _soilgrids_wcs(lat: float, lon: float, client: httpx.Client) -> dict | None:
    try:
        ph10 = _wcs_cell("phh2o", lat, lon, client)
        if ph10 is None:
            return None
        soc = _wcs_cell("soc", lat, lon, client)
    except (httpx.HTTPError, OSError, ValueError):
        return None
    return {"ph": round(ph10 / 10, 1), "soc_g_per_kg": round(soc / 10, 1) if soc else None,
            "clay_pct": None, "nitrogen_g_per_kg": None,
            "source": "ISRIC SoilGrids 2.0 (250 m map estimate, 0-5 cm, via WCS)"}


PH_BANDS = [
    (5.5, {"en": "strongly acidic", "hi": "बहुत अम्लीय", "mr": "जास्त आम्लधर्मी"}),
    (6.5, {"en": "slightly acidic", "hi": "हल्का अम्लीय", "mr": "किंचित आम्लधर्मी"}),
    (7.5, {"en": "neutral", "hi": "उदासीन (सामान्य)", "mr": "उदासीन (सामान्य)"}),
    (8.5, {"en": "slightly alkaline", "hi": "हल्का क्षारीय", "mr": "किंचित अल्कधर्मी"}),
    (99, {"en": "alkaline", "hi": "क्षारीय", "mr": "अल्कधर्मी"}),
]


def ph_band(ph: float, lang: str) -> str:
    for hi, text in PH_BANDS:
        if ph < hi:
            return tr(text, lang)
    return ""
