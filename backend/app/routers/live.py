"""Live field walk over a WebSocket.

Protocol (JSON messages):
  client -> {"type": "start", "lang": "mr", "mode": "walk"|"video", "lat": ..., "lon": ...}
  server -> {"type": "ready", "context": {...}, "guide": {...}, "photo_model": true}
  client -> {"type": "frame", "seq": 7, "data": "<base64 JPEG, <=400 KB>", "at": 12.0}
             ("at": seconds into the file, video only — where a finding was seen)
  server -> {"type": "frame", "seq": 7, "quality": {...}, "counted": bool, "advanced": bool,
             "live": {"top": [...]} | null, "guide": {...}}
  server -> {"type": "ask", "cue_id", "question", "candidates"}      (at most once)
  client -> {"type": "answer", "cue_id": "...", "answer": "yes|no|unknown"}
  server -> {"type": "steps_done"}                                   (all views collected)
  client -> {"type": "end_of_video"}                                 (video: no more frames)
  client -> {"type": "finish", "send_to_expert": false}
  server -> {"type": "summary", "summary": {...}}  and closes.

A disconnect before "finish" saves nothing, but the session waits a few minutes
for the caller to dial back in ({"type": "resume", "token": ...}) — a walk and a
video alike, and, when REDIS_URL is set, on whichever API container the
reconnection lands. Frames are decoded in memory and dropped; only evidence
frames for a finding are written, as problem photos.

Two sources feed the same machinery. A phone walks the field and is guided view
by view. A computer cannot be carried there, so it reads a video the farmer
filmed earlier: the frames arrive the same way, but nothing is asked for and
nothing is coached — the video is already shot. Either way a problem is reported
as seen only when two separate frames agree.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import logging
import math
import secrets
import time
from dataclasses import dataclass

from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app import auth, cache, config, live
from app.db import SessionLocal, get_db
from app.engine.livescan import decode
from app.kb import KB, get_kb, tr
from app.models import Farm, LiveScan

router = APIRouter(prefix="/api", tags=["live"], dependencies=[Depends(auth.require())])
MAX_FRAME_BYTES = 400_000
MAX_FRAMES = 600
MAX_SECONDS = 600
#: How long a connection may stay silent before it is treated as gone. The phone
#: sends a frame about twice a second while walking and a ping while it waits
#: for the farmer to answer a question, so silence this long means the phone is
#: asleep, flat or out of signal — not that somebody is thinking.
IDLE_SECONDS = 90
#: How long a caller has to say what they want after connecting.
OPENING_SECONDS = 15
#: The outside edge of a call. MAX_SECONDS stops new frames but still lets the
#: farmer finish and keep what they walked; this is the point where a socket is
#: let go whatever it claims to be doing, so a stream of pings cannot hold a
#: place in the queue for ever.
HARD_SECONDS = MAX_SECONDS + 180
#: Past HARD_SECONDS only the farmer's last word is taken — and only for this
#: long. After it nothing is, so the edge holds whatever a caller sends.
LAST_WORD_SECONDS = 60
#: Messages that are not messages — not JSON, not an object — a call will put
#: up with before it is let go. A phone on a bad link garbles the odd one; a
#: client that sends nothing else is not a call.
MAX_BAD_MESSAGES = 20
#: The longest position in a file a frame may claim to come from. The client
#: reads three minutes; this is only what stops a made-up number being stored.
MAX_AT_SECONDS = 3600.0
from app.i18n import LANGS  # noqa: E402

T = TypeVar("T")
log = logging.getLogger(__name__)


def _number(v: object, lo: float, hi: float) -> float | None:
    """`v` as a finite number within [lo, hi], or None.

    What arrives on the socket is whatever the other end chose to send, and
    JSON as Python reads it allows NaN, Infinity and true where a number was
    expected. A latitude of NaN goes on to be rounded, stored and handed to a
    weather service; it is cheaper to refuse it at the door."""
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    try:
        f = float(v)          # a 400-digit integer is valid JSON and no float
    except OverflowError:
        return None
    return f if math.isfinite(f) and lo <= f <= hi else None


async def _receive(ws: WebSocket, seconds: float) -> dict | None:
    """The next message, or None for something that was not one.

    receive_json raises on text that is not JSON and on a binary frame, and a
    list or a bare string parses perfectly well and then has no .get. Any of
    them used to end the call with an unhandled error — and, because the error
    skipped the parking below, took the farmer's walk with it."""
    try:
        msg = await asyncio.wait_for(ws.receive_json(), seconds)
    except (ValueError, KeyError):
        return None
    return msg if isinstance(msg, dict) else None


@contextmanager
def _db() -> Iterator[Session]:
    """A database session for one piece of work, and not a moment longer.

    A call lasts minutes. A pooled connection does not belong to anyone for
    minutes: the pool holds fifteen, and behind PgBouncer's transaction pooling
    an open transaction pins a server connection too. Keeping one for the length
    of a walk means fifteen farmers can stop the whole application, and an idle
    transaction that outlives the pooler's patience is cut from under the call
    anyway. So the database is opened for the opening checks, for the context,
    and for the save at the end — never across the frames, which need none of it.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


#: A call whose connection dropped, kept warm for a short while so the farmer
#: can pick it up where it fell over. A walk is five minutes in a field on a
#: patchy network: dropping it means they walk it again from the edge of the
#: field, which is the quickest way to make a flagship feature unusable.
#:
#: Each parked call holds its evidence frames — three per problem, three
#: close-ups — so a couple of megabytes at worst, and the number of them is
#: capped, in all and per caller. They are held here first, in this process's
#: memory. With REDIS_URL set they are then moved to Redis (see "Held calls
#: every container can reach" below), because behind a load balancer the
#: phone's reconnection usually lands on another container; without it, or
#: while Redis is down, they stay here, which is the single-container case.
_parked: dict[str, "_Parked"] = {}
RESUME_SECONDS = 180
MAX_PARKED = 24
#: Held calls one caller may have at once. Calls are capped per caller while
#: they run; without this, the same account could open, drop and re-open its
#: way through every held place and push out a farmer's real walk.
MAX_PARKED_PER_CALLER = 3
#: Answers that were saved but may not have arrived, kept apart from the walks
#: above. Every finished call leaves one, and none of them may cost a dropped
#: walk its place.
_answered: dict[str, "_Parked"] = {}
MAX_ANSWERED = 64


@dataclass
class _Parked:
    at: float
    farm_id: int
    user_id: int | None
    sess: object
    ctx: dict
    lang: str
    spent: float
    #: A call that was saved, kept only so its answer can be given again. The
    #: line that drops in the second between the save and the summary arriving
    #: used to leave the farmer told their walk was lost, with the result of it
    #: sitting in their history.
    summary: dict | None = None
    #: Every token this call can be picked up with. Usually one; two while a
    #: reconnection has been handed a new token but not yet shown it arrived.
    aliases: tuple[str, ...] = ()


def _drop_held(table: dict[str, "_Parked"], p: "_Parked") -> None:
    for t in p.aliases:
        table.pop(t, None)


def _sweep_parked(now: float) -> None:
    for table, cap in ((_parked, MAX_PARKED), (_answered, MAX_ANSWERED)):
        for p in {id(p): p for p in table.values() if now - p.at > RESUME_SECONDS}.values():
            _drop_held(table, p)
        # Counted per call, not per token: one call held under two names is
        # still one place.
        held = sorted({id(p): p for p in table.values()}.values(), key=lambda p: p.at)
        for p in held[:max(0, len(held) - cap)]:
            _drop_held(table, p)


def _hold(tokens: tuple[str, ...], parked: "_Parked") -> None:
    """Keep a call for dialling back in, under each token that may come back."""
    parked.aliases = tuple(t for t in tokens if t)
    table = _answered if parked.summary is not None else _parked
    if table is _parked:
        mine = sorted({id(p): p for p in _parked.values() if p.user_id == parked.user_id}.values(),
                      key=lambda p: p.at)
        for p in mine[:max(0, len(mine) - MAX_PARKED_PER_CALLER + 1)]:
            _drop_held(_parked, p)
    for t in parked.aliases:
        table[t] = parked
    _sweep_parked(parked.at)


def _unpark(token: str, farm_id: int, user_id: int | None) -> "_Parked | None":
    """Pick a dropped call back up. The token alone is not enough: it must be
    the same field and the same person, so a token that leaked is still useless
    to anybody else."""
    now = time.monotonic()
    _sweep_parked(now)
    for table in (_parked, _answered):
        p = table.get(token)
        if p is None or p.farm_id != farm_id or p.user_id != user_id or now - p.at > RESUME_SECONDS:
            continue
        # Picked up once, under whichever name: none of them may pick it up
        # again, or two connections would be driving the one walk.
        _drop_held(table, p)
        return p
    return None


@dataclass
class _OnTheLine:
    """A call whose connection is still open, as far as this server knows.

    A phone that moves from wifi to its mobile network leaves the old
    connection half-open: nothing on it says it has gone, and the server only
    finds out when it has heard nothing for a minute and a half. Its
    reconnection arrives long before that, finds no held call — the walk is
    still attached to the dead connection — and used to be told the walk was
    gone. With this, the reconnection takes the call over instead."""
    task: asyncio.Task
    farm_id: int
    user_id: int | None
    gone: asyncio.Event
    #: Saving: the answer is being written and must be let finish, not cut off.
    saving: bool = False
    #: Reading a frame: the model is at work on a thread, changing the walk as
    #: it goes. A cancel cannot stop that thread, only stop waiting for it, so
    #: cut here the walk was held — and, with Redis, written out for another
    #: container — half-way through a frame, and the rest of that frame then
    #: landed on a copy nobody would see. A frame takes a moment; it is let finish.
    reading: bool = False
    #: Asked to hand over to a reconnection, rather than ended by anything else.
    taken: bool = False


_on_the_line: dict[str, _OnTheLine] = {}
#: How long a reconnection waits for the connection it is replacing to let go:
#: a save under way included (the pool waits up to thirty seconds for a
#: connection), and then a little.
TAKEOVER_SECONDS = 35.0


async def _take_over(token: str, farm_id: int, user_id: int | None) -> None:
    """If this token's call is still attached to an open connection, have that
    connection hand it over, and wait until it has."""
    line = _on_the_line.get(token)
    if line is None or line.farm_id != farm_id or line.user_id != user_id:
        return
    deadline = time.monotonic() + TAKEOVER_SECONDS
    while not line.gone.is_set() and time.monotonic() < deadline:
        if not line.saving and not line.reading and not line.taken:
            line.taken = True
            line.task.cancel()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(line.gone.wait(), 0.2)


# --------------------------------------------------------------------------
# Held calls every container can reach
# --------------------------------------------------------------------------
#
# With more than one API container behind a load balancer, the phone's
# reconnection usually lands on a different container from the one its call
# fell off. Held only in that container's memory, the walk was there, intact,
# and the farmer was told it was lost. So when REDIS_URL is set a held call is
# moved into Redis, and a reconnection that finds nothing anywhere asks every
# container, over a channel, to let go of a call still attached to a line it
# cannot see.
#
# Without REDIS_URL none of this runs and the memory tables above are the
# whole story, exactly as before. While Redis is down (app.cache's pattern: one
# failure and the process stops asking for a minute) a call simply stays in
# memory, where a reconnection to the same container still finds it.
#
# Layout, all under cache.NS:
#   live:call:<id>       the held call, once, as JSON         TTL what is left of RESUME_SECONDS
#   live:token:<token>   which call a token picks up, whose   TTL the same
#   live:held            walks held, by when (the total cap)
#   live:held:by:<user>  walks held by one caller (the per-caller cap)
#   live:answered        saved answers held to be given again (their own cap)
#   live:handing:<token> "this container has that call and is letting it go"
#   live:release         channel: "whoever has <token> on a line, let go"

try:
    #: Redis answered and said no — as against not answering. Only the second
    #: is Redis being down; marking it down for a refused record would take
    #: the whole process off Redis (shared caches, rate limits) for a minute
    #: because one farmer's video was large.
    from redis.exceptions import ResponseError as RedisRefused
except ImportError:      # no client library: nothing can raise it
    class RedisRefused(Exception):  # type: ignore[no-redef]
        pass

_K = cache.NS + "live:"
K_CALL = _K + "call:"
K_TOKEN = _K + "token:"
K_HELD = _K + "held"
K_HELD_BY = _K + "held:by:"
K_ANSWERED = _K + "answered"
K_HANDING = _K + "handing:"
RELEASE = _K + "release"
#: The shape of a held call in Redis; see LiveSession.to_state for why a
#: container must refuse a shape it does not know rather than guess.
HELD_VERSION = 1
#: How long a reconnection waits for some container to say it has the call.
#: Nobody answering means nobody has it: the walk is gone (or its container
#: is), and the farmer is told so in a second and a half rather than thirty-five.
ACK_SECONDS = 1.5
#: How often a reconnection looks for a call another container is letting go.
POLL_SECONDS = 0.15

#: Moves into Redis that have started and not finished, under every token the
#: call answers to. A reconnection to this container waits for one before it
#: looks: halfway through a move, a call is in both places at once.
_moving: dict[str, asyncio.Task] = {}
#: Background work that must not be collected half-done (asyncio keeps only a
#: weak reference to a task).
_background: set[asyncio.Task] = set()
_listener: asyncio.Task | None = None


def _shared() -> bool:
    """Whether held calls are kept where every container can reach them. Read
    each time rather than once at import, the way app.cache reads it."""
    return bool(cache.REDIS_URL)


def _spawn(coro) -> asyncio.Task:
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


async def _redis():
    """The shared client, or None while Redis is not configured or is down.
    Off the loop: the first call connects, and a dead host takes seconds to say so."""
    return await run_in_threadpool(cache.client) if _shared() else None


def _held_to_json(p: _Parked) -> str:
    """A held call as JSON — never a pickle, which anyone able to write to Redis
    could make run code in the API. `at` is this process's monotonic clock and
    means nothing elsewhere, so the moment it was held travels as wall time."""
    age = max(0.0, time.monotonic() - p.at)
    sess = p.sess.to_state() if p.sess is not None else None   # type: ignore[attr-defined]
    return json.dumps({"v": HELD_VERSION, "held_at": time.time() - age, "farm": p.farm_id, "user": p.user_id,
                       "sess": sess, "ctx": p.ctx, "lang": p.lang, "spent": p.spent, "summary": p.summary,
                       "aliases": list(p.aliases)}, ensure_ascii=False)


def _held_from_json(raw: str, kb: KB) -> _Parked:
    """The record _held_to_json wrote. Raises ValueError on anything else."""
    try:
        d = json.loads(raw)
        if not isinstance(d, dict) or d.get("v") != HELD_VERSION:
            raise ValueError("held call version %r" % (d.get("v") if isinstance(d, dict) else None,))
        sess = live.restore_session(kb, d["sess"]) if d.get("sess") is not None else None
        if sess is None and d.get("summary") is None:
            raise ValueError("a held call with neither a walk nor an answer")
        age = max(0.0, time.time() - float(d["held_at"]))
        return _Parked(time.monotonic() - age, int(d["farm"]), None if d["user"] is None else int(d["user"]),
                       sess, dict(d.get("ctx") or {}), str(d["lang"]), float(d["spent"]), d.get("summary"),
                       tuple(str(t) for t in d.get("aliases") or ()))
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"held call unreadable: {type(e).__name__}: {e}") from e


def _caller_key(user_id: int | None) -> str:
    return "-" if user_id is None else str(user_id)


def _unlist(r, cid: str) -> None:
    """Take a call out of every count it is in. `r` may be a pipeline."""
    r.zrem(K_HELD, cid)
    r.zrem(K_ANSWERED, cid)
    r.zrem(K_HELD_BY + cid.split("~", 1)[0], cid)


def _evict(r, cid: str) -> None:
    """Drop a held call from Redis and from every count it is in. Its tokens
    are left to expire: each now points at nothing, which picks up nothing.
    `r` may be a pipeline."""
    r.delete(K_CALL + cid)
    _unlist(r, cid)


def _put(r, p: _Parked, raw: str) -> None:
    """Hold `p` in Redis under every token it answers to, and keep the same
    caps the memory tables keep, counted per call, not per token: per caller
    first, then in all. Blocking: run off the loop.

    Held for what is left of its few minutes, not a fresh few: a call that
    sat in memory while Redis was down, and is moved once it is back, must
    not outlive the time a farmer was promised by however long the outage was.

    Two round trips to Redis rather than a dozen — this runs as a call ends,
    and on a deploy the container may have little time left. The writes go
    together in one MULTI; only the pushing out of the oldest follows, once
    the counts are known. Two containers holding at the same instant can
    leave one over for a moment and the next hold trims it: a cap exact at
    every instant would need a script, and this one exists to bound memory
    and to stop one caller crowding out the rest, which a moment's overshoot
    does neither."""
    age = max(0.0, time.monotonic() - p.at)
    ttl = math.ceil(RESUME_SECONDS - age)
    if ttl <= 0:
        return      # its time is up; nothing to carry anywhere
    now, held_at, u = time.time(), time.time() - age, _caller_key(p.user_id)
    # The caller is part of the id so a call pushed out of the total can be
    # taken out of its caller's count too, without reading it back.
    cid = f"{u}~{secrets.token_urlsafe(18)}"
    ref = json.dumps({"id": cid, "farm": p.farm_id, "user": p.user_id})
    counts = ([(K_ANSWERED, MAX_ANSWERED)] if p.summary is not None
              else [(K_HELD_BY + u, MAX_PARKED_PER_CALLER), (K_HELD, MAX_PARKED)])
    pipe = r.pipeline()
    pipe.set(K_CALL + cid, raw, ex=ttl)
    for t in p.aliases:
        pipe.set(K_TOKEN + t, ref, ex=ttl)
    for key, _ in counts:
        pipe.zadd(key, {cid: held_at})
        pipe.zremrangebyscore(key, "-inf", now - RESUME_SECONDS)   # past their time: already expired
        pipe.expire(key, RESUME_SECONDS + 60)
        pipe.zrange(key, 0, -1)                                     # oldest first
    try:
        out = pipe.execute()
    except RedisRefused:
        # Redis answered, and said no: a record over the store's request size
        # (a long video's evidence frames), or a store out of memory. Part of
        # a MULTI may have been applied before the refusal, so what did land
        # is taken back — a call reachable both here and in Redis could be
        # picked up twice and saved twice. Then the caller keeps it in memory.
        with contextlib.suppress(Exception):
            r.delete(K_CALL + cid, *(K_TOKEN + t for t in p.aliases))
        raise
    first = 1 + len(p.aliases)
    over: list[str] = []
    for i, (_, cap) in enumerate(counts):
        held = [c for c in out[first + 4 * i + 3] if c not in over]
        over += held[:max(0, len(held) - cap)]
    if over:
        # The call itself is held by now. Failing to push out older ones must
        # not read as failing to hold it: the caller would keep its memory
        # copy too, and a walk in two places can be picked up twice.
        try:
            pipe = r.pipeline()
            for old in over:
                _evict(pipe, old)
            pipe.execute()
        except Exception as e:  # noqa: BLE001  the next hold trims them
            log.warning("live: could not push out %d older held calls (%s)", len(over), type(e).__name__)


def _take(r, token: str, farm_id: int, user_id: int | None, kb: KB) -> _Parked | None:
    """Pick a held call up out of Redis, if it is this field's and this caller's.

    GETDEL on the call itself is the one step that decides who has it. Every
    token a call answers to points at the same record, so however many
    containers reach for it, under whichever of its names, exactly one gets
    it and the rest get nothing. The ownership check comes before it, from
    the token's own small record: a token that leaked, tried against the
    wrong field, is refused without destroying the farmer's walk.
    Blocking: run off the loop."""
    ref = r.get(K_TOKEN + token)
    if not ref:
        return None
    try:
        ref = json.loads(ref)
        cid = str(ref["id"])
        if ref.get("farm") != farm_id or ref.get("user") != user_id:
            return None
    except (ValueError, KeyError, TypeError):
        return None
    raw = r.getdel(K_CALL + cid)
    if raw is None:
        return None      # taken a moment ago, under this name or another
    try:
        p = _held_from_json(raw, kb)
    except ValueError:
        # Gone either way now; say so loudly, because the farmer is about to
        # be told their walk was lost and the reason is on this side.
        log.exception("live: a held call for farm %s could not be read back", farm_id)
        p = None
    # Tidying only: the GETDEL above already made this call ours, and every
    # name it had now points at nothing. A Redis that drops in between must
    # not cost the farmer a walk this container is already holding.
    try:
        pipe = r.pipeline()
        pipe.delete(*{K_TOKEN + t for t in ((p.aliases if p else ()) + (token,))})
        _unlist(pipe, cid)
        pipe.execute()
    except Exception as e:  # noqa: BLE001
        cache._down(e)
    return p


def _held_here(token: str) -> _Parked | None:
    return _parked.get(token) or _answered.get(token)


async def _move(p: _Parked) -> None:
    """Move a call held in this process's memory into Redis.

    It is held in memory first, synchronously, because it is held from the
    `finally` of a call that is ending, where nothing may wait; this follows
    on. Until it is done a reconnection here waits for it (see _pick_up), so
    the call is never in reach in two places at once. If Redis is down the
    call stays where it is."""
    try:
        try:
            r = await _redis()
        except Exception:  # noqa: BLE001  app.cache already logged and marked it down
            return
        if r is None or all(_held_here(t) is not p for t in p.aliases):
            return     # no Redis, or picked up or pushed out while this waited
        try:
            raw = await run_in_threadpool(_held_to_json, p)
        except Exception:  # noqa: BLE001  a bug here is not Redis being down
            log.exception("live: could not write a held call for farm %s as data; kept in memory", p.farm_id)
            return
        try:
            await run_in_threadpool(_put, r, p, raw)
        except RedisRefused as e:
            log.warning("live: Redis refused a held call for farm %s (%s, %d bytes); kept in memory",
                        p.farm_id, e, len(raw))
            return
        except Exception as e:  # noqa: BLE001
            cache._down(e)
            return
        _drop_held(_answered if p.summary is not None else _parked, p)
    finally:
        me = asyncio.current_task()
        for t in p.aliases:
            if _moving.get(t) is me:
                _moving.pop(t, None)


def _start_move(p: _Parked) -> asyncio.Task:
    task = _spawn(_move(p))
    for t in p.aliases:
        _moving[t] = task
    return task


def _keep(tokens: tuple[str, ...], parked: _Parked) -> None:
    """Hold a call for dialling back in: here at once, and in Redis too when
    there is one. Never waits, so it is safe from a `finally`."""
    _hold(tokens, parked)
    if _shared() and parked.aliases:
        _start_move(parked)


async def drain(timeout: float = 5.0) -> None:
    """Let the calls on their way into Redis get there, for a process that is
    stopping.

    A rolling deploy closes every live connection on the old container, and
    each call is held as it ends — in memory first, then moved. The memory
    goes with the container; only the move makes the walk reachable from the
    new one, and a loop that is being shut down cancels a move it was not told
    to wait for. Meant for the lifespan's shutdown, after the connections have
    closed. Without REDIS_URL there is never anything to wait for."""
    pending = {t for t in _moving.values() if not t.done()}
    if pending:
        await asyncio.wait(pending, timeout=timeout)


async def _take_shared(token: str, farm_id: int, user_id: int | None, kb: KB) -> _Parked | None:
    try:
        r = await _redis()
        return await run_in_threadpool(_take, r, token, farm_id, user_id, kb) if r is not None else None
    except Exception as e:  # noqa: BLE001
        cache._down(e)
        return None


async def _pick_up(token: str, farm_id: int, user_id: int | None, kb: KB) -> _Parked | None:
    """A held call, from this process's memory or from Redis."""
    pending = _moving.get(token)
    if pending is not None:
        # Halfway into Redis: let it land, then take it from wherever it is.
        with contextlib.suppress(Exception):
            await asyncio.shield(pending)
    p = _unpark(token, farm_id, user_id)
    if p is not None or not token or not _shared():
        return p
    return await _take_shared(token, farm_id, user_id, kb)


async def _from_elsewhere(token: str, farm_id: int, user_id: int | None, kb: KB) -> _Parked | None:
    """Ask every container to let go of this call, and wait for it to arrive.

    The cross-container half of _take_over. A phone that moved networks left
    its old connection open on another container, with the walk attached to
    it. That container answers by marking the token as being handed over,
    cuts the old line exactly as a takeover here does (never mid-save), and
    holds the call in Redis, where this picks it up."""
    if not token or not _shared():
        return None
    try:
        r = await _redis()
        if r is None:
            return None
        await run_in_threadpool(r.publish, RELEASE, json.dumps({"token": token, "farm": farm_id, "user": user_id}))
        began, acked = time.monotonic(), False
        while True:
            got = await run_in_threadpool(_take, r, token, farm_id, user_id, kb)
            if got is not None:
                return got
            waited = time.monotonic() - began
            if await run_in_threadpool(r.get, K_HANDING + token):
                acked = True
            elif acked or waited > ACK_SECONDS:
                # Nobody has it — or whoever had it is done handing it over,
                # and wrote it before saying so. One last look either way.
                return await run_in_threadpool(_take, r, token, farm_id, user_id, kb)
            if waited > TAKEOVER_SECONDS:
                return None
            await asyncio.sleep(POLL_SECONDS)
    except Exception as e:  # noqa: BLE001
        cache._down(e)
        return None


async def _on_release(token: str, farm_id: int, user_id: int | None) -> None:
    """Another container's reconnection wants this call. If it is here — on a
    line, or held in memory because Redis was down when it dropped — hand it
    over through Redis. The token alone is not enough, as everywhere else: it
    must be the same field and the same person."""
    line = _on_the_line.get(token)
    if line is not None and (line.farm_id != farm_id or line.user_id != user_id):
        line = None
    held = _held_here(token)
    if held is not None and (held.farm_id != farm_id or held.user_id != user_id):
        held = None
    if line is None and held is None:
        return
    r = await _redis()
    if r is None:
        return
    try:
        await run_in_threadpool(r.set, K_HANDING + token, cache.INSTANCE, ex=int(TAKEOVER_SECONDS) + 5)
    except Exception as e:  # noqa: BLE001
        cache._down(e)
        return
    try:
        if line is not None:
            await _take_over(token, farm_id, user_id)   # parks it, and starts its move
        pending = _moving.get(token)
        if pending is None and (held := _held_here(token)) is not None \
                and held.farm_id == farm_id and held.user_id == user_id:
            pending = _start_move(held)                 # held while Redis was down
        if pending is not None:
            await asyncio.shield(pending)
    finally:
        # Only once the call is in Redis (or is not coming): the reconnection
        # takes this going away as the cue for its last look.
        with contextlib.suppress(Exception):
            await run_in_threadpool(r.delete, K_HANDING + token)


def _subscriber():
    """A client for listening on the release channel. Asynchronous, so one
    subscription costs this process no thread while it waits."""
    import redis.asyncio as aredis  # noqa: PLC0415

    return aredis.from_url(cache.REDIS_URL, decode_responses=True, socket_connect_timeout=5,
                           health_check_interval=30)


async def _listen() -> None:
    """Run for the life of the process: act on releases from other containers.
    Reconnects after a failure, as app.cache.listen does, and stops on a
    shutdown that arrives in the middle of a reconnection."""
    while True:
        try:
            async with _subscriber() as client, client.pubsub() as ps:
                await ps.subscribe(RELEASE)
                async for msg in ps.listen():
                    if msg.get("type") != "message":
                        continue
                    try:
                        m = json.loads(msg["data"])
                        token, farm_id = str(m["token"]), int(m["farm"])
                        user_id = None if m.get("user") is None else int(m["user"])
                    except (ValueError, KeyError, TypeError):
                        continue
                    # Its own task: a hand-over waits for a save to finish, and
                    # the next release must not wait behind it.
                    _spawn(_on_release(token, farm_id, user_id))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise asyncio.CancelledError from e
            log.warning("live: release channel %s; reconnecting", type(e).__name__)
            await asyncio.sleep(5)


def _listen_lazily() -> None:
    """One listener per process, started by the first live call rather than at
    start-up: the lifespan is not this router's to change, and a process that
    never takes a live call has nothing to let go of."""
    global _listener
    if not _shared():
        return
    loop = asyncio.get_running_loop()
    if _listener is None or _listener.done() or _listener.get_loop() is not loop:
        _listener = loop.create_task(_listen())


_calls: Counter[int | None] = Counter()


def _in_progress() -> int:
    return sum(_calls.values())


@contextmanager
def _one_more_call(user_id: int | None) -> Iterator[None]:
    """Count the calls in flight, and whose they are. A single worker's event
    loop runs them all, so a plain counter is the whole of it — nothing else
    runs between the read and the write.

    Counting by caller as well as in total matters: a cap that only counts the
    total is a cap one account can fill on its own."""
    _calls[user_id] += 1
    try:
        yield
    finally:
        _calls[user_id] -= 1
        if _calls[user_id] <= 0:
            del _calls[user_id]


async def _in_db(work: Callable[[Session], T]) -> T:
    """Run `work` on a short-lived session, off the event loop.

    These calls go to a database that may be a continent away. Awaiting them on
    the loop itself would stall every other request on the worker for as long as
    the round trip takes.
    """
    def run() -> T:
        with _db() as db:
            return work(db)
    return await run_in_threadpool(run)


@router.get("/farms/{farm_id}/live/context")
def live_context(farm_id: int, lat: float | None = None, lon: float | None = None, accuracy: float | None = None,
                 lang: str = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = db.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")
    return live.context(db, kb, farm, lat, lon, accuracy, lang if lang in LANGS else "en")


@router.get("/farms/{farm_id}/live/{scan_id}")
def live_summary(farm_id: int, scan_id: int, lang: str = "en", db: Session = Depends(get_db),
                 kb: KB = Depends(get_kb)):
    """A finished walk's summary in `lang` — for a language switch on the summary screen."""
    scan = db.get(LiveScan, scan_id)
    if scan is None or scan.farm_id != farm_id:
        raise HTTPException(404, "live check not found")
    return live.render(db, kb, db.get(Farm, farm_id), scan, lang if lang in LANGS else "en")


@router.websocket("/live/{farm_id}")
async def live_ws(ws: WebSocket, farm_id: int):
    await ws.accept()
    kb = get_kb()
    _listen_lazily()

    def may_open(db: Session) -> tuple[str | None, str, int | None]:
        """Whether this call may happen, the field's own language, and who is
        calling. Read, and then let the connection go: nothing below here needs
        the database."""
        farm = db.get(Farm, farm_id)
        if farm is None:
            return "FARM_NOT_FOUND", "en", None
        user = auth.ws_user(ws, db)
        if not auth.can_open_farm(user, farm, db):
            return "NOT_ALLOWED", "en", None
        # A live walk records a scan against the field it is pointed at, and
        # the shared demo fields are everybody's. Reading one is fine; walking
        # one with a camera writes to what the next visitor sees.
        if auth.is_shared_demo(farm):
            return "DEMO_READ_ONLY", "en", None
        return None, farm.lang, (user.id if user else None)

    refusal, farm_lang, user_id = await _in_db(may_open)
    if refusal:
        await ws.send_json({"type": "error", "code": refusal})
        await ws.close(code=1000 if refusal == "FARM_NOT_FOUND" else 1008)
        return

    # A socket that connects and then says nothing is not a call and is not
    # charged as one: counting it would let anyone hold every place in the
    # queue just by opening connections and going quiet.
    try:
        start = await _receive(ws, OPENING_SECONDS)
    except (TimeoutError, WebSocketDisconnect):
        with contextlib.suppress(Exception):
            await ws.close(code=1000)
        return
    start = start or {}
    opening = start.get("type")
    if opening not in ("start", "resume"):
        await ws.send_json({"type": "error", "code": "EXPECTED_START"})
        await ws.close()
        return

    # Every frame of every call runs the model on a worker thread. Past a point
    # more callers do not mean more throughput, only that each one waits longer
    # and all of them time out together. Turning the next caller away with a
    # reason they can act on beats degrading the calls already under way.
    if _in_progress() >= config.LIVE_MAX_CALLS or _calls[user_id] >= config.LIVE_MAX_PER_CALLER:
        await ws.send_json({"type": "error", "code": "TOO_BUSY"})
        await ws.close(code=1013)
        return

    # Set before the try, because a drop part-way through setting a call up
    # lands in the handler below with none of this assigned.
    sess, ctx, lang, resume_token, settled = None, {}, farm_lang, "", True
    presented, heard, began = "", False, time.monotonic()
    line = _OnTheLine(asyncio.current_task(), farm_id, user_id, asyncio.Event())

    with _one_more_call(user_id):
        try:

            if opening == "resume":
                token = str(start.get("token") or "")
                await _take_over(token, farm_id, user_id)
                picked = await _pick_up(token, farm_id, user_id, kb)
                if picked is None:
                    # Still on a line, but on another container's.
                    picked = await _from_elsewhere(token, farm_id, user_id, kb)
                if picked is None:
                    # Too long ago, a container that is gone, or not theirs.
                    # Nothing is wrong with the connection: the client starts
                    # a fresh walk.
                    await ws.send_json({"type": "error", "code": "RESUME_UNKNOWN"})
                    await ws.close()
                    return
                if picked.summary is not None:
                    # Already saved; only the answer went missing on the way.
                    await ws.send_json({"type": "summary", "summary": picked.summary})
                    await ws.close()
                    return
                sess, ctx, lang, spent = picked.sess, picked.ctx, picked.lang, picked.spent
                presented = str(start.get("token"))
            else:
                lang = start.get("lang") if start.get("lang") in LANGS else farm_lang
                mode = "video" if start.get("mode") == "video" else "walk"
                lat, lon = _number(start.get("lat"), -90, 90), _number(start.get("lon"), -180, 180)
                # A video was filmed in the field and is being read at a desk.
                # Where the desk is says nothing about the crop: the weather
                # "right now" would be the town's, and a farmer at home would
                # be told they are forty kilometres from their own field.
                if lat is None or lon is None or mode == "video":
                    lat = lon = None
                accuracy = _number(start.get("accuracy"), 0, 1_000_000) if lat is not None else None

                def begin(db: Session):
                    farm = db.get(Farm, farm_id)
                    return (live.context(db, kb, farm, lat, lon, accuracy, lang),
                            live.new_session(kb, farm, lang, mode))

                ctx, sess = await _in_db(begin)
                spent = 0.0

            # What a dropped connection would come back with. Spent on first
            # use, so every reconnection is handed a fresh one.
            resume_token = secrets.token_urlsafe(24)
            for t in (resume_token, presented):
                if t:
                    _on_the_line[t] = line
            # Time already spent carries across a reconnection, so a call cannot
            # be stretched past its limit by dropping and dialling back in.
            began, announced_done = time.monotonic() - spent, False
            # From here the call is worth holding if the line goes — including
            # while "ready" is still on its way. A walk taken off the shelf for
            # a reconnection that drops again in that instant used to be held
            # nowhere at all.
            settled = False
            await ws.send_json({"type": "ready", "context": ctx, "guide": sess.guide(),
                                "photo_model": sess.can_classify, "resume": resume_token,
                                "resumed": opening == "resume"})

            async def announce_done() -> None:
                """Everything that is going to be looked at has been. Ask the Doubt
                Doctor question if two problems are still competing, then hand over."""
                nonlocal announced_done
                if announced_done:
                    return
                cue = sess.pending_question(kb)
                if cue:
                    a, b = cue["pair"]
                    await ws.send_json({"type": "ask", "cue_id": cue["id"],
                                        "question": tr(cue["question"], lang),
                                        "candidates": [kb.target_view(a, lang), kb.target_view(b, lang)]})
                await ws.send_json({"type": "steps_done", "asked": bool(cue)})
                announced_done = True

            bad, over_time = 0, False
            while True:
                try:
                    msg = await _receive(ws, IDLE_SECONDS)
                except TimeoutError:
                    break   # gone quiet: hold the walk, hand the place back
                if not heard and presented:
                    _on_the_line.pop(presented, None)   # "ready", and its token, arrived
                heard = True   # the other end is there, so "ready" reached it
                if msg is None:
                    bad += 1
                    if bad > MAX_BAD_MESSAGES:
                        break
                    await ws.send_json({"type": "error", "code": "BAD_MESSAGE"})
                    continue
                kind = msg.get("type")
                # Past this point a call is let go whatever it is sending —
                # except the farmer's own last word. A walk finished slowly,
                # over a long look-alike question, used to be refused at the
                # very end: the finish was dropped at this gate, the walk was
                # held, handed back, and refused again until the phone gave up.
                elapsed = time.monotonic() - began
                # The last word is the finish, or the one answer to a question
                # still waiting for it. Not "answer" as such: let through any
                # number of times, that was a way to hold a place in the queue
                # for ever past the edge meant to end exactly that.
                last_word = kind == "finish" or (
                    kind == "answer" and sess.asked is not None and sess.answer is None)
                if elapsed > HARD_SECONDS + LAST_WORD_SECONDS:
                    break
                if elapsed > HARD_SECONDS and not last_word:
                    if not over_time:
                        over_time = True
                        await ws.send_json({"type": "error", "code": "SESSION_LIMIT"})
                        continue
                    break
                if kind == "frame":
                    if sess.frames >= MAX_FRAMES or time.monotonic() - began > MAX_SECONDS:
                        await ws.send_json({"type": "error", "code": "SESSION_LIMIT"})
                        continue
                    try:
                        jpeg = base64.b64decode(msg.get("data") or "", validate=True)
                    except (binascii.Error, ValueError):
                        await ws.send_json({"type": "error", "code": "BAD_FRAME", "seq": msg.get("seq")})
                        continue
                    if not jpeg or len(jpeg) > MAX_FRAME_BYTES:
                        await ws.send_json({"type": "error", "code": "FRAME_SIZE", "seq": msg.get("seq")})
                        continue
                    try:
                        img = await run_in_threadpool(decode, jpeg)
                    except Exception:  # noqa: BLE001  unreadable frame: skip it, keep the call going
                        await ws.send_json({"type": "error", "code": "BAD_FRAME", "seq": msg.get("seq")})
                        continue
                    line.reading = True     # not to be cut off half-read (see _OnTheLine)
                    try:
                        out = await run_in_threadpool(sess.on_frame, img, jpeg,
                                                      live.classify if sess.can_classify else None,
                                                      _number(msg.get("at"), 0, MAX_AT_SECONDS))
                    finally:
                        line.reading = False
                    await ws.send_json({"type": "frame", "seq": msg.get("seq")} | out)
                    if sess.done:
                        await announce_done()
                elif kind == "end_of_video" and sess.mode == "video":
                    # The file ran out. However much of it was worth reading is what
                    # the summary is built from — a thin reading goes to an expert.
                    sess.ended = True
                    await announce_done()
                elif kind == "skip":
                    # The farmer cannot get this view. Moving on beats coaching
                    # towards a picture that does not exist until the clock runs
                    # out; the evidence rules already handle a thinner walk.
                    if sess.skip():
                        await ws.send_json({"type": "guide", "guide": sess.guide(), "advanced": True})
                        if sess.done:
                            await announce_done()
                elif kind == "answer":
                    sess.on_answer(str(msg.get("cue_id")), str(msg.get("answer")))
                    await ws.send_json({"type": "answered"})
                elif kind == "finish":
                    to_expert = bool(msg.get("send_to_expert"))

                    def save(db: Session):
                        farm = db.get(Farm, farm_id)
                        # Minutes have passed. The session that opened this call may
                        # have been signed out, revoked or expired since; a walk that
                        # is nobody's any more is not written to anybody's field.
                        if farm is None or not auth.can_open_farm(auth.ws_user(ws, db), farm, db):
                            return None
                        return live.finish(db, kb, farm, sess, ctx, lang, to_expert)

                    try:
                        # Not to be cut off by a reconnection mid-write: it
                        # waits for this instead (see _take_over).
                        line.saving = True
                        try:
                            summary = await asyncio.shield(_in_db(save))
                        finally:
                            line.saving = False
                    except asyncio.CancelledError:
                        raise
                    except Exception:  # noqa: BLE001
                        # The database blinked at the one moment that mattered.
                        # Nothing was written (the session rolled back), and the
                        # walk is still here in memory — so say so and stay on
                        # the line. Ending the call would throw away five
                        # minutes in a field over a connection reset.
                        log.exception("live: could not save the call for farm %s", farm_id)
                        await ws.send_json({"type": "error", "code": "SAVE_FAILED"})
                        continue
                    settled = True
                    if summary is None:
                        await ws.send_json({"type": "error", "code": "NOT_ALLOWED"})
                        await ws.close(code=1008)
                        return
                    # Held for a few minutes under the token the phone already
                    # has, in case this send is the one that does not arrive.
                    _keep((resume_token,), _Parked(time.monotonic(), farm_id, user_id, None, {}, lang, 0.0, summary))
                    await ws.send_json({"type": "summary", "summary": summary})
                    await ws.close()
                    return
                elif kind == "lang" and msg.get("lang") in LANGS:  # switched language mid-call
                    lang = msg["lang"]
                    live.relang(kb, sess, lang)
                    ctx = live.localize_context(kb, ctx, lang)
                    await ws.send_json({"type": "lang", "lang": lang, "context": ctx, "guide": sess.guide()})
                elif kind == "ping":
                    await ws.send_json({"type": "pong"})
        except WebSocketDisconnect:
            pass  # nothing was written, so there is nothing to undo
        except asyncio.CancelledError:
            if not line.taken:
                raise   # the server is stopping, not a reconnection
            # A reconnection is taking this call over: hold it for that, below.
            # The cancel was ours and has been answered; without taking it
            # back, the timeouts awaited below would read it as still pending.
            task = asyncio.current_task()
            if task is not None:
                task.uncancel()
        except Exception:  # noqa: BLE001
            # Something broke that was not the network — a frame the model
            # choked on, say. The call ends, but not the walk: it is parked
            # below like any other drop, and the phone dials straight back in.
            log.exception("live: the call for farm %s ended on an error", farm_id)
        finally:
            # Every way out of a call comes through here, the early ones too:
            # one that skipped this left its line registered as still open,
            # and the next reconnection with its token sat waiting on a call
            # that had already ended. Nothing in here waits, so nothing — a
            # reconnection's takeover included — can interrupt it half-done.
            #
            # Dropped, gone quiet, or simply out of time: the walk itself is
            # worth something. A farmer halfway down a field on a patchy
            # network should not have to start again at the gate, so the
            # session waits a few minutes for them to dial back in. A video is
            # held the same way: three minutes of footage read to the last ten
            # seconds is not something to make anybody sit through twice.
            #
            # Held under the token "ready" handed over — and, when nothing has
            # been heard since, under the one the phone dialled in with too: a
            # "ready" sent into a line that had already gone never told the
            # phone its new token, and it will come back with the old one.
            #
            # Only a call with something in it is held — a frame that was worth
            # reading — and only one that could still be finished: well past
            # the outside edge, holding it would only hand back a call that can
            # do nothing but run out of time again.
            now = time.monotonic()
            if (not settled and sess is not None and sess.good_frames
                    and now - began < HARD_SECONDS + RESUME_SECONDS):
                tokens = (resume_token,) + ((presented,) if presented and not heard else ())
                _keep(tokens, _Parked(now, farm_id, user_id, sess, ctx, lang, now - began))
            for t, held in list(_on_the_line.items()):
                if held is line:
                    _on_the_line.pop(t, None)
            line.gone.set()

        with contextlib.suppress(Exception):
            # A connection that has gone half-open will not answer a close;
            # do not wait on it.
            await asyncio.wait_for(ws.close(code=1001), 2)
