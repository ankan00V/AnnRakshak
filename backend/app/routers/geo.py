"""Where the farm is (app/geo.py) — used by the sign-up screens.

  GET /api/geo/places               every state and district (Government's LGD list)
  GET /api/geo/reverse?lat=&lon=    the state, district and village at a point
  GET /api/geo/search?q=            villages and towns in India matching a name

Open to signed-out visitors: this is what sign-up asks before an account exists.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app import geo
from app.limits import client_ip, limit

router = APIRouter(prefix="/api/geo", tags=["geo"])


@router.get("/places")
def all_places():
    return {"states": [{"name": s, "districts": v["districts"]} for s, v in geo.places().items()]}


@router.get("/reverse")
def reverse(request: Request, lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    limit(f"geo:{client_ip(request)}", 60, 300)
    return geo.reverse(lat, lon) or {"state": None, "district": None, "village": None}


@router.get("/search")
def search(request: Request, q: str = Query(min_length=2, max_length=80)):
    limit(f"geo:{client_ip(request)}", 60, 300)
    return {"results": geo.search(q)}
