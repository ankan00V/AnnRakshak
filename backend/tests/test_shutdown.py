"""A restart must not wait on an open stream.

The farmer app holds one SSE stream per open tab. Before this, the stream
watched only the client and its own five-minute deadline, so uvicorn's
graceful shutdown — which waits for every connection to close — sat at
"Waiting for connections to close" for the rest of those five minutes. Every
save in development, every deploy in production, where the platform's own
patience runs out first and SIGKILL lands instead, so the orderly shutdown
the lifespan goes to such trouble over never runs at all.

These pin the flag's behaviour rather than the stream's wall-clock, which is
the part a test can state without being slow or flaky. The suite has no async
tests and no asyncio plugin configured, so each one drives its own loop.
"""

from __future__ import annotations

import asyncio

import pytest

from app import runtime


@pytest.fixture(autouse=True)
def _fresh_flag():
    """Each test gets its own process-lifetime flag."""
    runtime._flag = None
    yield
    runtime._flag = None


def test_waiting_before_startup_does_not_claim_shutdown():
    """Unarmed, `wait()` must block.

    A handler exercised outside the app would otherwise be told at once to
    shut down something that never started.
    """
    async def go():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(runtime.wait(), timeout=0.05)

    asyncio.run(go())
    assert runtime.is_stopping() is False


def test_armed_flag_blocks_until_shutdown_begins():
    async def go():
        runtime.arm()
        assert runtime.is_stopping() is False
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(runtime.wait(), timeout=0.05)

        runtime.begin()

        assert runtime.is_stopping() is True
        # The point of the whole exercise: a waiter returns at once, so the
        # connection closes and the process can go.
        await asyncio.wait_for(runtime.wait(), timeout=0.5)

    asyncio.run(go())


def test_every_waiter_is_woken_not_just_the_first():
    """One stream per open tab, so shutdown has to release all of them."""
    async def go():
        runtime.arm()
        waiters = [asyncio.ensure_future(runtime.wait()) for _ in range(5)]
        await asyncio.sleep(0)
        assert not any(w.done() for w in waiters)

        runtime.begin()
        done, pending = await asyncio.wait(waiters, timeout=0.5)

        assert not pending
        assert len(done) == 5

    asyncio.run(go())


def test_begin_without_arm_is_harmless():
    """Shutdown can run after a startup that failed before arming."""
    runtime.begin()  # must not raise
    assert runtime.is_stopping() is False


def test_a_queue_read_loses_nothing_when_shutdown_races_it():
    """The pattern the stream uses, in miniature.

    `asyncio.wait` leaves the losing future pending rather than cancelling
    it, which is why the stream keeps its `q.get()` across keep-alives: a
    cancelled read that had already taken an event off the queue would drop
    it, and that event is somebody's spray warning.
    """
    async def go():
        runtime.arm()
        q: asyncio.Queue[str] = asyncio.Queue()
        stopping = asyncio.ensure_future(runtime.wait())
        pending_get = asyncio.ensure_future(q.get())

        # A keep-alive tick: nothing arrives, and the read survives it.
        done, _ = await asyncio.wait({pending_get, stopping}, timeout=0.05,
                                     return_when=asyncio.FIRST_COMPLETED)
        assert not done
        assert not pending_get.done()

        await q.put("spray-warning")
        done, _ = await asyncio.wait({pending_get, stopping}, timeout=0.5,
                                     return_when=asyncio.FIRST_COMPLETED)
        assert pending_get in done
        assert pending_get.result() == "spray-warning"

        stopping.cancel()

    asyncio.run(go())
