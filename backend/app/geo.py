"""Where the farm is, anywhere in India.

Three things the sign-up screen needs:

  places()             every state and district, from the Government's Local
                       Government Directory (backend/kb/india_districts.json)
  reverse(lat, lon)    the state, district and village at a point — so a farmer
                       standing in the field taps once and the form fills itself
  locate(state, ...)   coordinates for a place typed by hand, because the
                       weather, the spray window and the outbreak radius are all
                       read at a point, not at a district name

The two network lookups are best-effort: on any failure the farmer simply fills
the form in themselves, which is why nothing here raises.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache

import httpx

from app import cache
from app.config import KB_DIR

TIMEOUT_S = 8.0
CACHE_DAYS = 30
UA = "AnnRakshak/1.0 (Smart India Hackathon 2026 crop advisory; +https://github.com/annrakshak)"
REVERSE_URL = "https://api.bigdatacloud.net/data/reverse-geocode-client"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
SEARCH_URL = "https://geocoding-api.open-meteo.com/v1/search"


@lru_cache(maxsize=1)
def places() -> dict:
    """{state: {"districts": [{"name", "local"}]}} — 785 districts, as the
    Government of India publishes them."""
    data = json.loads((KB_DIR / "india_districts.json").read_text(encoding="utf-8"))
    return {s: {"districts": [{"name": d["name"], "local": d["local"]} for d in v["districts"]]}
            for s, v in data["states"].items()}


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return re.sub(r"[^a-z]", "", s.replace("district", ""))


def match_district(state: str | None, district: str | None) -> tuple[str | None, str | None]:
    """A state and district from any source, snapped to the official names when
    they match; otherwise returned as given (a new district, or a spelling we
    don't know, is still a real place)."""
    all_places = places()
    state_hit = next((s for s in all_places if _norm(s) == _norm(state)), None)
    if state_hit is None:
        return (state or None), (district or None)
    hit = next((d["name"] for d in all_places[state_hit]["districts"] if _norm(d["name"]) == _norm(district)), None)
    return state_hit, hit or (district or None)


def _cached(key: str, fetch) -> dict | list | None:
    hit = cache.get_json(key)
    if hit is not None:
        return hit
    out = fetch()
    if out:
        cache.set_json(key, out, ttl_s=CACHE_DAYS * 86400)
    return out


def reverse(lat: float, lon: float) -> dict | None:
    """{'state', 'district', 'village'} at a point, or None if no service answers."""
    key = f"geo:rev:{round(lat, 3)},{round(lon, 3)}"

    def fetch() -> dict | None:
        with httpx.Client(timeout=TIMEOUT_S, headers={"User-Agent": UA}) as c:
            out = _big_data_cloud(c, lat, lon) or _nominatim(c, lat, lon)
        if not out:
            return None
        state, district = match_district(out.get("state"), out.get("district"))
        return {"state": state, "district": district, "village": out.get("village")}

    return _cached(key, fetch)  # type: ignore[return-value]


def _big_data_cloud(c: httpx.Client, lat: float, lon: float) -> dict | None:
    try:
        r = c.get(REVERSE_URL, params={"latitude": lat, "longitude": lon, "localityLanguage": "en"})
        j = r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return None
    if j.get("countryCode") != "IN":
        return None
    admin = {a.get("adminLevel"): a.get("name") for a in (j.get("localityInfo") or {}).get("administrative") or []}
    return {"state": j.get("principalSubdivision") or admin.get(4),
            "district": admin.get(5) or j.get("city"),
            "village": j.get("locality") or j.get("city")}


def _nominatim(c: httpx.Client, lat: float, lon: float) -> dict | None:
    try:
        r = c.get(NOMINATIM_URL, params={"lat": lat, "lon": lon, "format": "json", "zoom": 12, "accept-language": "en"})
        a = (r.json() if r.status_code == 200 else {}).get("address") or {}
    except (httpx.HTTPError, ValueError):
        return None
    if a.get("country_code") != "in":
        return None
    return {"state": a.get("state"), "district": a.get("state_district") or a.get("county"),
            "village": a.get("village") or a.get("town") or a.get("city") or a.get("suburb")}


def search(q: str, limit: int = 8) -> list[dict]:
    """Villages and towns in India matching what the farmer typed:
    [{'name', 'taluka', 'district', 'state', 'lat', 'lon'}]."""
    q = " ".join((q or "").split())
    if len(q) < 3:
        return []

    def fetch() -> list[dict]:
        try:
            with httpx.Client(timeout=TIMEOUT_S, headers={"User-Agent": UA}) as c:
                r = c.get(SEARCH_URL, params={"name": q, "count": 20, "language": "en", "format": "json"})
            results = (r.json() if r.status_code == 200 else {}).get("results") or []
        except (httpx.HTTPError, ValueError):
            return []
        out = []
        for x in results:
            if x.get("country_code") != "IN":
                continue
            state, district = match_district(x.get("admin1"), x.get("admin2"))
            out.append({"name": x.get("name"), "taluka": x.get("admin3"), "district": district,
                        "state": state, "lat": x.get("latitude"), "lon": x.get("longitude")})
        return out[:limit]

    return _cached(f"geo:q:{q.lower()}", fetch) or []  # type: ignore[return-value]


def locate(state: str | None, district: str | None, village: str | None = None) -> dict | None:
    """Coordinates for a place the farmer typed, most specific first. None when
    nothing answers — the app then has to ask for the location itself."""
    for q in ([f"{village}, {district}" if village and district else village,
               f"{district}, {state}" if district and state else district, state]):
        for hit in search(q or "", limit=8):
            if state and hit["state"] and _norm(hit["state"]) != _norm(state):
                continue
            if hit["lat"] is not None:
                return {"lat": hit["lat"], "lon": hit["lon"], "state": hit["state"] or state,
                        "district": hit["district"] or district, "matched": hit["name"]}
    return None
