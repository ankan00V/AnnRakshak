"""A dropped live call, picked back up on whichever container the phone reaches.

Behind a load balancer the reconnection usually lands on a different API
container from the one the call fell off. These tests run without a real
Redis: a small stand-in below gives the calls the router makes their Redis
meaning, and "another container" is simulated by emptying this process's own
tables between the drop and the reconnection, so the only thing that can carry
the walk across is Redis.
"""

import asyncio
import json
import re
import threading
import time

import pytest

from app import cache, live
from app.engine.livescan import STATE_VERSION, LiveSession
from app.routers import live as R
import test_live
from test_live import frame_msg, kb, leaf, read_video, summary_of

#: The farm, the weather and the model the live tests run against, shared.
client = test_live.client

# --- a Redis that lives in this process ----------------------------------------


class FakeRedis:
    """Just the commands the app uses, with Redis's meaning, one at a time.

    `down` makes every command fail the way a dropped Redis connection does,
    for the fallback tests."""

    def __init__(self):
        self.lock = threading.RLock()
        self.kv: dict[str, tuple[object, float | None]] = {}
        self.z: dict[str, dict[str, float]] = {}
        self.subs: list[tuple[str, asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self.published: list[tuple[str, str]] = []
        self.down = False

    def _up(self):
        if self.down:
            raise ConnectionError("redis is down")

    def _live(self, key):
        v = self.kv.get(key)
        if v is not None and v[1] is not None and v[1] <= time.time():
            del self.kv[key]
            return None
        return v

    def ping(self):
        self._up()
        return True

    def get(self, key):
        with self.lock:
            self._up()
            v = self._live(key)
            return v[0] if v else None

    def set(self, key, value, ex=None, nx=False):
        with self.lock:
            self._up()
            if nx and self._live(key):
                return None
            self.kv[key] = (value, time.time() + ex if ex else None)
            return True

    def getdel(self, key):
        with self.lock:
            self._up()
            v = self._live(key)
            self.kv.pop(key, None)
            return v[0] if v else None

    def delete(self, *keys):
        with self.lock:
            self._up()
            n = 0
            for k in keys:
                n += (self.kv.pop(k, None) is not None) + (self.z.pop(k, None) is not None)
            return n

    def expire(self, key, seconds):
        with self.lock:
            self._up()
            v = self._live(key)
            if v:
                self.kv[key] = (v[0], time.time() + seconds)
            return True

    def incr(self, key):
        with self.lock:
            self._up()
            v = self._live(key)
            n = int(v[0]) + 1 if v else 1
            self.kv[key] = (str(n), v[1] if v else None)
            return n

    def pipeline(self):
        fake = self

        class Pipe:
            def __init__(self):
                self.ops = []

            def __getattr__(self, name):
                return lambda *a, **k: self.ops.append((name, a, k))

            def execute(self):
                return [getattr(fake, n)(*a, **k) for n, a, k in self.ops]

        return Pipe()

    def zadd(self, key, mapping):
        with self.lock:
            self._up()
            self.z.setdefault(key, {}).update({m: float(s) for m, s in mapping.items()})

    def zrem(self, key, *members):
        with self.lock:
            self._up()
            zs = self.z.get(key, {})
            return sum(zs.pop(m, None) is not None for m in members)

    def zrange(self, key, start, end):
        with self.lock:
            self._up()
            ordered = [m for m, _ in sorted(self.z.get(key, {}).items(), key=lambda kv: kv[1])]
            return ordered[start:] if end == -1 else ordered[start:end + 1]

    def zremrangebyscore(self, key, lo, hi):
        with self.lock:
            self._up()
            zs = self.z.get(key, {})
            gone = [m for m, s in zs.items() if float(lo) <= s <= float(hi)]
            for m in gone:
                del zs[m]
            return len(gone)

    def publish(self, channel, message):
        with self.lock:
            self._up()
            self.published.append((channel, message))
            listeners = [(loop, q) for ch, loop, q in self.subs if ch == channel]
        for loop, q in listeners:
            loop.call_soon_threadsafe(q.put_nowait, {"type": "message", "channel": channel, "data": message})
        return len(listeners)

    # what is left in the store, for the assertions
    def calls(self) -> list[str]:
        with self.lock:
            return [k for k in self.kv if k.startswith(R.K_CALL) and self._live(k)]


class FakePubSub:
    def __init__(self, fake: FakeRedis):
        self.fake, self.queue, self.mine = fake, asyncio.Queue(), []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        with self.fake.lock:
            self.fake.subs = [s for s in self.fake.subs if s not in self.mine]

    async def subscribe(self, *channels):
        loop = asyncio.get_running_loop()
        with self.fake.lock:
            for ch in channels:
                entry = (ch, loop, self.queue)
                self.mine.append(entry)
                self.fake.subs.append(entry)

    async def listen(self):
        while True:
            yield await self.queue.get()


class FakeAsyncRedis:
    def __init__(self, fake: FakeRedis):
        self.fake = fake

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    def pubsub(self):
        return FakePubSub(self.fake)


@pytest.fixture()
def redis(client, monkeypatch):
    """Redis on, every container's tables empty, and a fresh listener."""
    fake = FakeRedis()
    monkeypatch.setattr(cache, "REDIS_URL", "redis://stand-in")
    monkeypatch.setattr(cache, "client", lambda: fake)
    monkeypatch.setattr(cache, "_down_until", 0.0)
    monkeypatch.setattr(R, "_subscriber", lambda: FakeAsyncRedis(fake))
    monkeypatch.setattr(R, "_listener", None)
    monkeypatch.setattr(R, "ACK_SECONDS", 0.4)
    another_container()
    yield fake
    another_container()


def another_container() -> None:
    """Forget everything this process holds, as a different container would
    know nothing of it. Whatever survives this is in Redis."""
    for table in (R._parked, R._answered, R._on_the_line, R._moving):
        table.clear()


def settled(timeout: float = 3.0) -> None:
    """The dropped call's handler runs on the server's thread, and its move
    into Redis after that; wait until both are done."""
    end = time.monotonic() + timeout
    while (R._in_progress() or R._moving) and time.monotonic() < end:
        time.sleep(0.02)
    assert not R._in_progress() and not R._moving, "the dropped call never settled"


def held_only_in_redis(fake: FakeRedis) -> None:
    settled()
    assert not R._parked and not R._answered, "the call is still in this container's memory"
    assert len(fake.calls()) == 1, "the call is not in Redis"


# --- a walk as data, exactly ----------------------------------------------------

def _walk_until(s: LiveSession, classify, there) -> None:
    seed = 4000
    while not there(s) and seed < 4200:
        s.on_frame(leaf(seed), f"w{seed}".encode(), classify, None)
        seed += 1


def _same_walk(a: LiveSession, b: LiveSession, next_frame, classify, at=None) -> None:
    assert b.findings(kb) == a.findings(kb)
    assert b.guide() == a.guide()
    assert b.why_thin() == a.why_thin()
    assert b.reading() == a.reading()
    img, data = next_frame
    assert b.on_frame(img, data, classify, at) == a.on_frame(img, data, classify, at), \
        "the walk picked up did not take the next frame as the dropped one would have"
    assert b.to_state() == a.to_state()
    assert b.findings(kb) == a.findings(kb)


def test_a_walk_held_mid_way_comes_back_exactly_as_it_was():
    """Mid-walk: a glimpse that added the "show me more of those" step, views
    half collected, evidence frames kept. Written out, read back, it must say
    the same things and take the next frame the same way — the farmer cannot
    be told something different because the call moved."""
    n = {"i": 0}

    def classify(img):
        n["i"] += 1
        if n["i"] == 3:
            return [("rice_brown_spot", 0.55), ("rice_healthy", 0.4), ("rice_blast", 0.02)]
        return [("rice_healthy", 0.92), ("rice_brown_spot", 0.05), ("rice_blast", 0.01)]

    s = LiveSession(crop="rice", lang="mr", can_classify=True, target_name=live._namer(kb, "mr"))
    # Into the step the glimpse added, one view of its three collected.
    _walk_until(s, classify, lambda s: not s.done and s.steps[s.idx].id == "confirm" and s.steps[s.idx].got == 1)
    assert not s.done and s.steps[s.idx].id == "confirm", "the walk did not reach the part worth testing"
    assert s.closeups and s.sightings and s._last_thumb is not None

    raw = json.dumps(s.to_state())                       # what goes over the wire: text, no pickle
    back = live.restore_session(kb, json.loads(raw))
    assert back.target_name("rice_brown_spot") == s.target_name("rice_brown_spot")  # in Marathi, still
    assert back.evidence_for("rice_brown_spot") == s.evidence_for("rice_brown_spot")
    _same_walk(s, back, (leaf(4999), b"next"), classify)


def test_a_video_held_mid_read_comes_back_exactly_as_it_was():
    readings = iter([[("rice_healthy", 0.93)], [("rice_brown_spot", 0.9)], [("rice_brown_spot", 0.86)],
                     [("maize_rust", 0.6)], [("rice_brown_spot", 0.88)], [("rice_brown_spot", 0.91)]] * 2)
    s = LiveSession(crop="rice", lang="hi", can_classify=True, mode="video",
                    target_name=live._namer(kb, "hi"))
    s.on_frame(leaf(1, dark=True), b"dark", lambda img: next(readings), at=0.0)    # passed over
    for i, seed in enumerate(range(4100, 4105)):
        s.on_frame(leaf(seed), f"v{seed}".encode(), lambda img: next(readings), at=1.0 + i * 1.5)
    s.pending_question(kb)
    assert s.marks and s.passed_over_why and s.evidence

    back = live.restore_session(kb, json.loads(json.dumps(s.to_state())))
    sure = lambda img: [("rice_brown_spot", 0.91), ("rice_healthy", 0.05)]  # noqa: E731
    _same_walk(s, back, (leaf(4200), b"next"), sure, at=12.5)
    # and the second that was in flight is still recognised as a repeat
    again = back.on_frame(leaf(4200), b"next", sure, at=12.5)
    assert again["repeat"]


def test_a_walk_written_by_another_version_is_refused_not_guessed_at():
    state = LiveSession(crop="rice", lang="en", can_classify=False).to_state()
    with pytest.raises(ValueError):
        LiveSession.from_state(state | {"v": STATE_VERSION + 1})
    with pytest.raises(ValueError):
        LiveSession.from_state(state | {"steps": [{"id": "dance", "kind": "close", "need": 1, "got": 0}]})
    with pytest.raises(ValueError):
        LiveSession.from_state({k: v for k, v in state.items() if k != "marks"})


# --- across containers, end to end ----------------------------------------------

def test_a_walk_dropped_on_one_container_is_picked_up_on_another(client, redis):
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "mr"})
        token = ws.receive_json()["resume"]
        for seq in range(2):
            ws.send_json(frame_msg(seq, 5000 + seq))
            m = ws.receive_json()
        assert (m["guide"]["step"], m["guide"]["got"]) == ("overview", 2)
    held_only_in_redis(redis)
    another_container()

    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        back = ws.receive_json()
        assert back["type"] == "ready" and back["resumed"], back
        assert (back["guide"]["step"], back["guide"]["got"]) == ("overview", 2)
        assert re.search("[ऀ-ॿ]", back["guide"]["text"]), "the walk came back in another language"
        ws.send_json(frame_msg(2, 5002))
        assert ws.receive_json()["advanced"], "the third overview view did not complete the step"


def test_a_video_dropped_on_one_container_is_finished_on_another(client, redis):
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = ws.receive_json()["resume"]
        read_video(ws, range(5100, 5104))
    held_only_in_redis(redis)
    another_container()

    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        back = ws.receive_json()
        assert back["resumed"] and back["guide"]["read"] == 4 and back["guide"]["kept"] == 4
        ws.send_json(frame_msg(9, 5110, at=9.0))
        assert ws.receive_json()["guide"]["kept"] == 5
        ws.send_json({"type": "end_of_video"})
        assert ws.receive_json()["type"] == "steps_done"
        ws.send_json({"type": "finish"})
        s = summary_of(ws)
    assert s["verdict"] == "found" and s["reading"]["read"] == 5
    assert s["seen"][0]["evidence"], "the evidence frames did not survive the move"


def test_an_answer_lost_on_the_way_is_given_again_by_another_container(client, redis):
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = ws.receive_json()["resume"]
        read_video(ws, range(5200, 5206))
        ws.send_json({"type": "end_of_video"})
        ws.receive_json()
        ws.send_json({"type": "finish"})
        first = summary_of(ws)
    held_only_in_redis(redis)
    another_container()
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        again = ws.receive_json()
        assert again["type"] == "summary" and again["summary"]["scan_id"] == first["scan_id"]


def test_the_old_token_still_works_on_another_container_when_ready_never_arrived(client, redis):
    """Picked back up, then dropped again before the new token reached the
    phone: the walk is held under both names, in Redis, and the phone's next
    try with the old one lands on yet another container."""
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        old = ws.receive_json()["resume"]
        read_video(ws, range(5300, 5304))
    held_only_in_redis(redis)
    another_container()
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": old})
        # "ready" is sent, and the line is gone before the phone says anything
    held_only_in_redis(redis)
    another_container()
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": old})
        back = ws.receive_json()
        assert back["resumed"] and back["guide"]["read"] == 4
        newer = back["resume"]
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"
    held_only_in_redis(redis)
    another_container()
    with client.websocket_connect("/api/live/1") as ws:      # one call, picked up once
        ws.send_json({"type": "resume", "token": old})
        assert ws.receive_json()["code"] == "RESUME_UNKNOWN"
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": newer})
        assert ws.receive_json()["guide"]["read"] == 4


def test_a_line_still_open_on_another_container_is_let_go_over_redis(client, redis, monkeypatch):
    """Wifi to mobile data: the old connection is still open on container A,
    the reconnection reaches container B. B cannot see A's line, so it asks
    over Redis; A cuts its line, holds the walk in Redis, and B picks it up."""
    real = R._take_over
    looked = []

    async def blind_on_b(token, farm_id, user_id):
        if not looked:            # B's own look: A's line is not in B's process
            looked.append(token)
            return
        await real(token, farm_id, user_id)   # A, answering the release

    with client.websocket_connect("/api/live/1") as old:
        old.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = old.receive_json()["resume"]
        read_video(old, range(5400, 5404))
        monkeypatch.setattr(R, "_take_over", blind_on_b)
        with client.websocket_connect("/api/live/1") as new:
            new.send_json({"type": "resume", "token": token})
            back = new.receive_json()
            assert back["type"] == "ready" and back["resumed"], back
            assert back["guide"]["read"] == 4
            new.send_json(frame_msg(9, 5410, at=9.0))
            assert new.receive_json()["guide"]["kept"] == 5
    assert looked == [token]
    sent = [json.loads(m) for ch, m in redis.published if ch == R.RELEASE]
    assert sent == [{"token": token, "farm": 1, "user": None}]


def test_a_token_nobody_holds_is_refused_quickly_even_with_redis(client, redis):
    began = time.monotonic()
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": "not-a-real-token"})
        assert ws.receive_json()["code"] == "RESUME_UNKNOWN"
    assert time.monotonic() - began < R.TAKEOVER_SECONDS / 4, "waited out a takeover nobody answered"


# --- the take, the caps, and what is refused -----------------------------------

def _walk_parked(user_id, farm_id=1, summary=None):
    sess = None if summary else LiveSession(crop="rice", lang="en", can_classify=False)
    return R._Parked(time.monotonic(), farm_id, user_id, sess, {}, "en", 3.0, summary)


def _put(fake, tokens, p):
    p.aliases = tuple(tokens)
    R._put(fake, p, R._held_to_json(p))


def test_two_containers_reaching_for_one_call_never_both_get_it():
    """Under each of its names, from many containers at once: exactly one gets it."""
    for attempt in range(5):
        fake = FakeRedis()
        _put(fake, ("new-name", "old-name"), _walk_parked(7))
        got, start = [], threading.Barrier(8)

        def reach(fake, token, start, got):
            start.wait()
            got.append(R._take(fake, token, 1, 7, kb))

        threads = [threading.Thread(target=reach, args=(fake, ("new-name", "old-name")[i % 2], start, got))
                   for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sum(p is not None for p in got) == 1, f"attempt {attempt}: {got}"
        assert not fake.calls() and R._take(fake, "old-name", 1, 7, kb) is None


def test_a_leaked_token_on_the_wrong_field_does_not_destroy_the_walk():
    fake = FakeRedis()
    _put(fake, ("t",), _walk_parked(7))
    assert R._take(fake, "t", 2, 7, kb) is None            # another field
    assert R._take(fake, "t", 1, 8, kb) is None            # another person
    assert R._take(fake, "t", 1, 7, kb) is not None        # still there for its farmer


def test_held_calls_are_capped_in_redis_as_in_memory():
    fake = FakeRedis()
    _put(fake, ("farmer-walk",), _walk_parked(7))
    for i in range(R.MAX_ANSWERED + 5):                      # a busy afternoon of finished calls
        _put(fake, (f"answer-{i}",), _walk_parked(8, summary={"x": i}))
    for i in range(5):                                       # one account, dropping over and over
        _put(fake, (f"spam-{i}",), _walk_parked(9))
    assert R._take(fake, "farmer-walk", 1, 7, kb) is not None, "a real dropped walk was pushed out"
    spam = [R._take(fake, f"spam-{i}", 1, 9, kb) for i in range(5)]
    assert [p is not None for p in spam] == [False, False, True, True, True], "not the newest three kept"
    answers = [R._take(fake, f"answer-{i}", 1, 8, kb) for i in range(R.MAX_ANSWERED + 5)]
    assert sum(p is not None for p in answers) == R.MAX_ANSWERED


def test_a_held_call_this_release_cannot_read_is_refused_not_crashed_on(client, redis):
    redis.set(R.K_TOKEN + "from-the-future", json.dumps({"id": "-~x", "farm": 1, "user": None}), ex=60)
    redis.set(R.K_CALL + "-~x", json.dumps({"v": R.HELD_VERSION + 1, "sess": {}}), ex=60)
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": "from-the-future"})
        assert ws.receive_json()["code"] == "RESUME_UNKNOWN"
    with client.websocket_connect("/api/live/1") as ws:      # and the server is still answering
        ws.send_json({"type": "start", "lang": "en"})
        assert ws.receive_json()["type"] == "ready"


# --- Redis down, and Redis not configured ------------------------------------

def test_with_redis_down_a_dropped_call_is_held_in_memory_instead(client, redis):
    redis.down = True
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = ws.receive_json()["resume"]
        read_video(ws, range(5500, 5504))
    settled()
    assert token in R._parked and not redis.kv, "the call should have stayed in memory"
    with client.websocket_connect("/api/live/1") as ws:      # the same container still has it
        ws.send_json({"type": "resume", "token": token})
        back = ws.receive_json()
        assert back["resumed"] and back["guide"]["read"] == 4


def test_a_call_held_in_memory_while_redis_was_down_reaches_another_container_once_it_is_back(
        client, redis, monkeypatch):
    redis.down = True
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = ws.receive_json()["resume"]
        read_video(ws, range(5600, 5604))
    settled()
    assert token in R._parked
    redis.down = False

    # Container B: its own memory has nothing; container A's does, and A
    # answers B's release by moving the call into Redis.
    real = R._unpark
    looked = []

    def blind_on_b(token, farm_id, user_id):
        looked.append(token)
        return None if len(looked) == 1 else real(token, farm_id, user_id)

    monkeypatch.setattr(R, "_unpark", blind_on_b)
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        back = ws.receive_json()
        assert back["resumed"] and back["guide"]["read"] == 4
        assert any(json.loads(m)["token"] == token for ch, m in redis.published if ch == R.RELEASE)
    # Dropped again, with Redis back: held there this time, not in memory.
    held_only_in_redis(redis)


def test_without_redis_nothing_is_asked_of_it(client, monkeypatch):
    """REDIS_URL unset — a laptop, the test suite, one container: no client is
    asked for, no listener started, and the call is held in memory exactly as
    before."""
    assert not cache.REDIS_URL
    monkeypatch.setattr(cache, "client", lambda: pytest.fail("Redis was asked for without REDIS_URL"))
    monkeypatch.setattr(R, "_listener", None)
    another_container()
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = ws.receive_json()["resume"]
        read_video(ws, range(5700, 5703))
    settled()
    assert token in R._parked and R._listener is None and not R._moving
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        assert ws.receive_json()["resumed"]



# --- after review: what a deploy and a slow save do to a held call -------------

def test_a_save_under_way_on_another_container_is_let_finish_and_its_answer_handed_across(
        client, redis, monkeypatch):
    """The farmer pressed finish, the save started on container A, and the
    phone changed networks in that second. The reconnection reaches B. A must
    not cut its line mid-write — the walk would be saved half or twice — but
    let the save finish, and B must hand the farmer that one saved answer."""
    from app.db import SessionLocal
    from app.models import LiveScan

    real_take_over, looked = R._take_over, []

    async def blind_on_b(token, farm_id, user_id):
        if not looked:            # B's own look: A's line is not in B's process
            looked.append(token)
            return
        await real_take_over(token, farm_id, user_id)   # A, answering the release

    real_finish, saving, go, handed_while_saving = live.finish, threading.Event(), threading.Event(), []

    def slow_finish(*a, **k):
        saving.set()
        assert go.wait(10), "the save was never let go on"
        return real_finish(*a, **k)

    def let_the_save_go_once_a_has_answered(token):
        end = time.monotonic() + 10
        while time.monotonic() < end and not redis.get(R.K_HANDING + token):
            time.sleep(0.01)
        line = R._on_the_line.get(token)
        handed_while_saving.append(bool(line and line.saving))
        go.set()

    monkeypatch.setattr(live, "finish", slow_finish)
    with client.websocket_connect("/api/live/1") as old:
        old.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = old.receive_json()["resume"]
        read_video(old, range(5800, 5806))
        old.send_json({"type": "end_of_video"})
        old.receive_json()
        monkeypatch.setattr(R, "_take_over", blind_on_b)
        threading.Thread(target=let_the_save_go_once_a_has_answered, args=(token,), daemon=True).start()
        old.send_json({"type": "finish"})
        assert saving.wait(5), "the save never started"
        with client.websocket_connect("/api/live/1") as new:
            new.send_json({"type": "resume", "token": token})
            handed = new.receive_json()
        first = summary_of(old)
    settled()
    assert handed_while_saving == [True], "A let go of the call before saying it was handing it over"
    assert handed["type"] == "summary", handed
    assert handed["summary"]["scan_id"] == first["scan_id"]
    with SessionLocal() as db:
        assert db.query(LiveScan).count() == 1, "the walk was saved twice"
    assert not redis.calls(), "the answer is still held after it was handed over"


def test_a_call_moved_late_keeps_only_the_time_it_had_left():
    """Held in memory while Redis was down and moved once it was back: the
    farmer was promised a few minutes, not a few minutes after the outage."""
    fake = FakeRedis()
    late = _walk_parked(7)
    late.at = time.monotonic() - (R.RESUME_SECONDS - 5)
    _put(fake, ("late",), late)
    for key in (R.K_TOKEN + "late", fake.calls()[0]):
        assert fake.kv[key][1] - time.time() <= 6, f"{key} was given a fresh few minutes"
    assert R._take(fake, "late", 1, 7, kb) is not None, "still inside its time, it must come back"

    gone = _walk_parked(7)
    gone.at = time.monotonic() - R.RESUME_SECONDS - 1
    _put(fake, ("gone",), gone)
    assert not fake.calls() and R._take(fake, "gone", 1, 7, kb) is None


def test_redis_dropping_just_after_the_take_does_not_cost_the_walk(monkeypatch):
    """The GETDEL decides who has the call. Redis going away in the moment
    after it, before the tidying, must not throw away a walk already in hand."""
    monkeypatch.setattr(cache, "_down_until", 0.0)
    monkeypatch.setattr(cache, "_client", None)

    class DropsAfterTheTake(FakeRedis):
        def getdel(self, key):
            got = super().getdel(key)
            self.down = True
            return got

    fake = DropsAfterTheTake()
    _put(fake, ("t",), _walk_parked(7))
    p = R._take(fake, "t", 1, 7, kb)
    assert p is not None and p.sess is not None and p.spent == 3.0
    assert cache._down_until > time.time(), "Redis failing was not noted, so it will be asked again at once"


def test_a_stopping_container_waits_for_its_held_calls_to_reach_redis(monkeypatch):
    """A deploy closes every live connection on the old container and each call
    is held as it ends. Memory goes with the container: a move the shutdown
    did not wait for is a walk no new container can find."""
    fake = FakeRedis()
    monkeypatch.setattr(cache, "REDIS_URL", "redis://stand-in")
    monkeypatch.setattr(cache, "client", lambda: fake)
    real_put = R._put

    def slow_put(r, p, raw):
        time.sleep(0.3)           # a Redis a continent away
        real_put(r, p, raw)

    monkeypatch.setattr(R, "_put", slow_put)
    another_container()

    async def stop():
        R._keep(("deploying",), _walk_parked(7))
        assert R._moving and not fake.calls()
        await R.drain(5)
        await R.drain(5)          # nothing left to wait for: returns at once

    try:
        asyncio.run(stop())
    finally:
        another_container()
    assert len(fake.calls()) == 1 and not R._moving
    assert R._take(fake, "deploying", 1, 7, kb) is not None


# --- second review: a frame in flight, and a Redis that refuses or half-answers --

def test_a_frame_being_read_when_another_container_takes_over_is_not_lost(client, redis, monkeypatch):
    """The phone changed networks while the model was reading a frame on
    container A. Cut there, the walk was written out for container B half-way
    through that frame — counted as clear, never as kept — and the model's
    reading then landed on a copy nobody would ever see. A must let the frame
    finish, so B carries on from a walk that is whole."""
    real_take_over, looked = R._take_over, []

    async def blind_on_b(token, farm_id, user_id):
        if not looked:
            looked.append(token)
            return
        await real_take_over(token, farm_id, user_id)

    real_classify, reading, go = live.classify, threading.Event(), threading.Event()

    def slow_classify(img):
        reading.set()
        assert go.wait(10), "the frame was never let finish"
        return real_classify(img)

    with client.websocket_connect("/api/live/1") as old:
        old.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = old.receive_json()["resume"]
        read_video(old, range(5900, 5904))
        monkeypatch.setattr(R, "_take_over", blind_on_b)
        monkeypatch.setattr(live, "classify", slow_classify)
        old.send_json(frame_msg(4, 5904, at=4.0))
        assert reading.wait(5), "the fifth frame never reached the model"
        threading.Timer(0.6, go.set).start()
        with client.websocket_connect("/api/live/1") as new:
            new.send_json({"type": "resume", "token": token})
            back = new.receive_json()
    assert back["type"] == "ready" and back["resumed"], back
    g = back["guide"]
    assert (g["read"], g["clear"], g["kept"]) == (5, 5, 5), f"the frame in flight was cut in half: {g}"


def test_a_call_redis_refuses_stays_here_and_does_not_take_the_process_off_redis(client, redis, monkeypatch):
    """Redis answering "no" — a long video's evidence over the store's request
    size, say — is not Redis being down. Read as down, one large walk took
    the whole process off Redis for a minute, shared caches and rate limits
    with it. The walk stays in memory, and nothing half-written of it is left
    in Redis for another container to pick up a second time."""
    exceptions = pytest.importorskip("redis.exceptions")
    real_set = redis.set

    def refusing(key, value, **kw):
        if key.startswith(R.K_TOKEN):      # the call itself has landed by now
            raise exceptions.ResponseError("max request size exceeded")
        return real_set(key, value, **kw)

    monkeypatch.setattr(redis, "set", refusing)
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = ws.receive_json()["resume"]
        read_video(ws, range(6000, 6004))
    settled()
    assert token in R._parked, "the refused walk was not kept in memory"
    assert not redis.calls(), "half of a refused call was left in Redis"
    assert cache._down_until == 0.0, "a refusal was taken for Redis being down"
    monkeypatch.setattr(redis, "set", real_set)
    with client.websocket_connect("/api/live/1") as ws:      # the same container still has it
        ws.send_json({"type": "resume", "token": token})
        back = ws.receive_json()
        assert back["resumed"] and back["guide"]["read"] == 4


def test_a_call_held_in_redis_is_not_kept_here_too_when_pushing_out_older_ones_fails(
        client, redis, monkeypatch):
    """The call was written to Redis; only the pushing out of this caller's
    oldest held call failed after it. Read as a failed hold, the walk was
    kept in this container's memory as well — two copies, one per container,
    that two reconnections could each pick up and each save."""
    for i in range(R.MAX_PARKED_PER_CALLER):
        _put(redis, (f"older-{i}",), _walk_parked(None))
    real_pipeline, made = redis.pipeline, []

    def pipeline():
        pipe = real_pipeline()
        made.append(pipe)
        if len(made) == 2:                  # after the write: the pushing out

            def lost():
                raise ConnectionError("connection reset")

            pipe.execute = lost
        return pipe

    monkeypatch.setattr(redis, "pipeline", pipeline)
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = ws.receive_json()["resume"]
        read_video(ws, range(6100, 6104))
    settled()
    assert len(made) >= 2, "the hold never had anything to push out"
    assert not R._parked, "the walk is held both here and in Redis"
    assert cache._down_until == 0.0
    another_container()
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        back = ws.receive_json()
        assert back["resumed"] and back["guide"]["read"] == 4
