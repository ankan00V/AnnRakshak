"""Start a long training run that outlives the shell that started it.

Three runs have now been lost part-way — one at epoch 9 — because a run started
with `nohup ... &` still sits in the calling shell's process group, and when the
terminal or the assistant session that owns that group goes away the whole group
is signalled. nohup only covers SIGHUP; the kill that arrives is a SIGTERM to
the group, and the training dies with a truncated traceback inside backward().

start_new_session=True calls setsid() in the child, so it leads its own session
and process group and belongs to no terminal. macOS has no setsid binary, which
is why this is a Python file and not a one-liner.

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
print(f"{child.pid}")
