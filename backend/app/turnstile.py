"""Cloudflare Turnstile: the box that says a person asked for this code.

One-time codes cost money and reach a real inbox, so the request for one is
the thing worth protecting — not the screen after it. A script can work
through a list of addresses at the rate limit and send a code to each; the
widget is what makes that cost something.

Configured with Cloudflare's own test keys by default (the ones that always
pass, published at developers.cloudflare.com/turnstile/troubleshooting/testing).
The widget is real, the verification call is real, and nothing is refused —
which is what a demo wants. Put the site's own keys in TURNSTILE_SITEKEY and
TURNSTILE_SECRET and the same code starts refusing bots.

When Cloudflare itself cannot be reached, the request is let through and the
failure logged. The code still goes to an email the caller has to open, and the
per-address and per-IP limits still stand: a Cloudflare outage should not stop
a farmer signing in.
"""

from __future__ import annotations

import logging

import httpx

from app.config import TURNSTILE_SECRET, TURNSTILE_SITEKEY

log = logging.getLogger("annrakshak.turnstile")

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT = 5.0


def configured() -> bool:
    return bool(TURNSTILE_SITEKEY and TURNSTILE_SECRET)


def verify(token: str | None, ip: str | None = None) -> tuple[bool, str | None]:
    """(passed, why not). Nothing configured: nothing to check."""
    if not configured():
        return True, None
    if not token:
        return False, "missing"
    data = {"secret": TURNSTILE_SECRET, "response": token}
    if ip:
        data["remoteip"] = ip
    try:
        r = httpx.post(VERIFY_URL, data=data, timeout=TIMEOUT)
        out = r.json()
    except Exception as e:  # noqa: BLE001  an outage must not lock anybody out
        log.warning("turnstile unreachable (%s); letting the request through", e)
        return True, None
    if out.get("success"):
        return True, None
    codes = ",".join(out.get("error-codes") or []) or "rejected"
    log.info("turnstile refused a request: %s", codes)
    return False, codes
