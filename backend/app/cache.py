"""Redis (Upstash) for what one process can't do alone, with an in-process
fallback so a Redis outage — or no REDIS_URL at all (tests, a laptop) —
degrades to single-instance behaviour instead of an error.

  get_json / set_json   shared cache (weather bundles, soil, translations)
  hit                   fixed-window rate limits (paid Sarvam calls, emails, pushes)
  leader                "only one watcher runs" across API instances
  publish / listen      in-app events to every instance's open app tabs (SSE)

Keys are namespaced 'ar:'. Values are JSON. Nothing secret is stored.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections.abc import Callable

from app.config import REDIS_URL

log = logging.getLogger("annrakshak.cache")
NS = "ar:"
EVENTS = NS + "events"
RETRY_AFTER_S = 60

_client = None
_down_until = 0.0
_lock = threading.Lock()
_mem: dict[str, tuple[float, object]] = {}
_counts: dict[str, tuple[float, int]] = {}
INSTANCE = f"{os.getpid()}-{time.time_ns()}"


def client():
    """The shared Redis client, or None while Redis is not configured or down."""
    global _client, _down_until
    if not REDIS_URL or time.time() < _down_until:
        return None
    if _client is None:
        with _lock:
            if _client is None:
                try:
                    import redis  # noqa: PLC0415

                    c = redis.from_url(REDIS_URL, socket_timeout=3, socket_connect_timeout=3,
                                       health_check_interval=30, decode_responses=True)
                    c.ping()
                    _client = c
                except Exception as e:  # noqa: BLE001
                    _down(e)
                    return None
    return _client


def _down(e: Exception) -> None:
    global _client, _down_until
    log.warning("redis unavailable (%s); using in-process fallback for %ss", type(e).__name__, RETRY_AFTER_S)
    _client, _down_until = None, time.time() + RETRY_AFTER_S


def available() -> bool:
    return client() is not None


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

def get_json(key: str):
    r = client()
    if r is not None:
        try:
            raw = r.get(NS + key)
            return json.loads(raw) if raw else None
        except Exception as e:  # noqa: BLE001
            _down(e)
    hit = _mem.get(key)
    return hit[1] if hit and hit[0] > time.time() else None


def set_json(key: str, value, ttl_s: int) -> None:
    r = client()
    if r is not None:
        try:
            r.set(NS + key, json.dumps(value, ensure_ascii=False), ex=ttl_s)
            return
        except Exception as e:  # noqa: BLE001
            _down(e)
    _mem[key] = (time.time() + ttl_s, value)


# --------------------------------------------------------------------------
# Rate limits and leadership
# --------------------------------------------------------------------------

def hit(key: str, window_s: int) -> int:
    """Count one event in the current fixed window; returns the count so far."""
    bucket = f"{NS}rl:{key}:{int(time.time() // window_s)}"
    r = client()
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incr(bucket)
            pipe.expire(bucket, window_s + 5)
            return int(pipe.execute()[0])
        except Exception as e:  # noqa: BLE001
            _down(e)
    exp, n = _counts.get(bucket, (time.time() + window_s, 0))
    _counts[bucket] = (exp, n + 1)
    for k in [k for k, (e, _) in _counts.items() if e < time.time()]:
        _counts.pop(k, None)
    return n + 1


def leader(name: str, ttl_s: int) -> bool:
    """True if this instance holds (or just took) the named lease. Without Redis
    every process is its own leader — the single-instance case."""
    r = client()
    if r is None:
        return True
    key = f"{NS}lease:{name}"
    try:
        if r.set(key, INSTANCE, nx=True, ex=ttl_s):
            return True
        if r.get(key) == INSTANCE:
            r.expire(key, ttl_s)
            return True
        return False
    except Exception as e:  # noqa: BLE001
        _down(e)
        return True


# --------------------------------------------------------------------------
# Events for open app tabs, across instances
# --------------------------------------------------------------------------

def publish(farm_id: int, event: dict) -> bool:
    """Send to every instance (each fans out to its own tabs). False = do it locally."""
    r = client()
    if r is None:
        return False
    try:
        r.publish(EVENTS, json.dumps({"farm_id": farm_id, "event": event}, ensure_ascii=False))
        return True
    except Exception as e:  # noqa: BLE001
        _down(e)
        return False


async def listen(deliver: Callable[[int, dict], object]) -> None:
    """Run forever: relay Redis events to this instance's tabs. Reconnects."""
    if not REDIS_URL:
        return
    import redis.asyncio as aredis  # noqa: PLC0415

    while True:
        try:
            r = aredis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5, health_check_interval=30)
            async with r.pubsub() as ps:
                await ps.subscribe(EVENTS)
                async for msg in ps.listen():
                    if msg.get("type") != "message":
                        continue
                    try:
                        m = json.loads(msg["data"])
                        deliver(int(m["farm_id"]), m["event"])
                    except (ValueError, KeyError, TypeError):
                        continue
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            # A shutdown that lands while the connection is being torn down
            # surfaces as the teardown's own error (a TimeoutError on a dead
            # socket), not as CancelledError. Treating that as a network blip
            # and reconnecting swallowed the shutdown, and the server hung on
            # "Waiting for application shutdown" and could not reload.
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise asyncio.CancelledError from e
            log.warning("redis events: %s; reconnecting", type(e).__name__)
            await asyncio.sleep(5)
