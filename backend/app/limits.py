"""Rate limits (fixed windows, shared across instances through Redis when it is
up). They protect what costs money or reaches people: paid Sarvam calls, emails
and phone notifications — not ordinary reads."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app import cache
from app.config import TRUST_PROXY


def limit(key: str, max_hits: int, window_s: int) -> None:
    if cache.hit(key, window_s) > max_hits:
        raise HTTPException(429, "too many requests — please wait a moment and try again",
                            headers={"Retry-After": str(window_s)})


def client_ip(request: Request) -> str:
    """Who to count a request against.

    X-Forwarded-For is a header the client can send. Believing it when nothing
    is in front of this server means a per-IP limit counts whatever the caller
    writes there — so the limit on sign-in codes, which exists to stop someone
    working through a phone book, stops nobody. It is read only when the
    operator says a proxy sets it (ANNRAKSHAK_TRUST_PROXY)."""
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
