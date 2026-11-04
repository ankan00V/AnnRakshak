"""One flag: the process is going away.

Uvicorn's graceful shutdown waits for every open connection to close, and a
streaming response is a connection that closes when the handler decides to.
So a handler that only watches the client and its own deadline will hold the
whole process open until that deadline — the farmer app keeps an SSE stream
per open tab, and a restart sat at "Waiting for connections to close" for the
stream's full five minutes with nothing to show for it.

In development that is every save. In production it is every deploy: the
platform waits, gives up, and sends SIGKILL instead, so the shutdown the
lifespan was careful to do properly never runs.

A long-lived handler waits on `shutting_down.wait()` alongside whatever else
it is waiting for, and returns as soon as it is set. The flag is created on
the running loop by `arm()` and set by `begin()`, both called from the
lifespan, so nothing here has to know what a stream is and a stream does not
have to import the app.
"""

from __future__ import annotations

import asyncio
import logging
import signal

log = logging.getLogger("annrakshak.runtime")

_flag: asyncio.Event | None = None


def arm() -> None:
    """Fresh flag for this process, set when the stop signal arrives.

    The signal, not the lifespan. Uvicorn stops accepting, *then* waits for
    open connections, and only *then* runs the shutdown half of the lifespan
    — so a flag set after `yield` is set long after the thing it was meant to
    unblock. The signal handler runs first, which is the whole point.

    Uvicorn has already installed its own handlers by the time the lifespan
    runs, so replacing them outright would break shutdown altogether. This
    chains: ours sets the flag and then calls theirs. If the previous handler
    cannot be read, nothing is installed and uvicorn's behaviour is left
    exactly as it was — a slow shutdown is a nuisance, one that never happens
    is a broken deploy.
    """
    global _flag
    _flag = asyncio.Event()

    loop = asyncio.get_running_loop()
    installed = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Uvicorn installs with signal.signal rather than the loop's own
        # add_signal_handler — deliberately, so it can restore what was there
        # before — so this is where its handler is found.
        prev = signal.getsignal(sig)
        if not callable(prev):  # SIG_DFL / SIG_IGN: nothing to chain to
            continue

        def chain(signum, frame, _prev=prev):
            # Waking the loop from a signal handler, rather than touching the
            # Event here, is the part that has to be thread-safe.
            loop.call_soon_threadsafe(begin)
            _prev(signum, frame)

        try:
            signal.signal(sig, chain)
        except (ValueError, OSError):  # not the main thread
            break
        installed.append(sig)

    if installed:
        log.debug("shutdown flag chained onto %s", [s.name for s in installed])


def begin() -> None:
    """The process is stopping. Wake everything waiting on it."""
    if _flag is not None:
        _flag.set()


def is_stopping() -> bool:
    return _flag is not None and _flag.is_set()


async def wait() -> None:
    """Return when the process starts shutting down.

    Before `arm()` — a unit test exercising a handler on its own, say — there
    is nothing to wake, so this waits forever rather than returning at once
    and telling the caller to shut down something that never started.
    """
    if _flag is None:
        await asyncio.Event().wait()
    else:
        await _flag.wait()
