"""What a held-out folder stands for, in a model that may have moved on.

Held-out images sit in folders named for the class they were collected as.
A later model can merge a class away — fall-armyworm damage is trained and
served as fall armyworm itself — and the folder keeps the old name, because
the images on disk are what they always were.

Three scripts read that split and each one died on the same KeyError in turn
(ml/live_eval.py, ml/tune_gate.py, ml/sample_outcomes.py). One definition here,
so the next model to merge a class breaks none of them.
"""

from __future__ import annotations


def target_of(folder: str, class_to_target: dict[str, str]) -> str | None:
    """The advisory target a folder's images stand for, or None when this model
    has no target for them at all — in which case the caller should say so and
    skip them, not guess."""
    if folder in class_to_target:
        return class_to_target[folder]
    targets = set(class_to_target.values())
    if folder in targets:
        return folder
    merged = folder.rsplit("_", 1)[0]          # ..._damage, ..._larvae
    if merged in class_to_target:
        return class_to_target[merged]
    return merged if merged in targets else None
