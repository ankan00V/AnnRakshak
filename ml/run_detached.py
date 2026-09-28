"""Start a long training run that outlives the shell that started it.

Three runs have now been lost part-way — one at epoch 9 — because a run started
with `nohup ... &` still sits in the calling shell's process group, and when the
terminal or the assistant session that owns that group goes away the whole group
is signalled. nohup only covers SIGHUP; the kill that arrives is a SIGTERM to
the group, and the training dies with a truncated traceback inside backward().

start_new_session=True calls setsid() in the child, so it leads its own session
and process group and belongs to no terminal. macOS has no setsid binary, which
is why this is a Python file and not a one-liner.

A fourth run then died at epoch 6 because detaching it was only half the
problem: the earlier `nohup` runs had been wrapped in `caffeinate -i`, that
wrapper went away with them, and an idle Mac went to sleep under the training.
So the run is started through `caffeinate -i -w <pid>`, which holds the
assertion for exactly as long as the training lives and releases it when the
run ends rather than leaving a laptop awake all night.

    .venv/bin/python ml/run_detached.py ml/train_v7.log ml/train.py --with-extra ...
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

if len(sys.argv) < 3:
    raise SystemExit(__doc__)

log_path, cmd = Path(sys.argv[1]), sys.argv[2:]
log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("wb") as log:
    child = subprocess.Popen(
        [sys.executable, *cmd],
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        start_new_session=True,  # its own session: no controlling terminal, its own process group
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        cwd=Path(__file__).resolve().parents[1],
    )
    # -w waits on the training's pid, so the Mac stays awake for exactly as long
    # as the run does. Detached the same way: it must not die with this shell
    # either, or the sleep it was holding off arrives anyway.
    subprocess.Popen(["caffeinate", "-i", "-w", str(child.pid)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
print(f"{child.pid}")
