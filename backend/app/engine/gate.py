"""The confidence gate. Every diagnosis passes through `decide()` and gets
exactly one outcome: advise, clarify (Doubt Doctor) or escalate (expert).

It is plain code comparing numbers to constants — the "never give a confident
wrong answer" promise is something you can point at, not a hope in a prompt.

Order matters:
  1. not a crop photo                     → retake
     not our crop                         → escalate
  2. top-1 below FLOOR                    → escalate
  3. top-1 and top-2 within MARGIN        → clarify if a cue separates them,
                                            else escalate
  4. clear but below GATE                 → escalate
     a lab-trained class below its own     → clarify if a cue separates it from
     higher bar (config.TARGET_GATE)          the runner-up, else escalate
  5. top-1 is inspection-tier             → escalate (a photo can't settle it)
  6. no advisory in the knowledge base    → escalate
  7. otherwise                            → advise

Ambiguity (3) is checked before the absolute gate (4): 0.52 vs 0.44 is worth a
question even though neither clears the gate, while 0.66 vs 0.10 is clear but
not confident enough, and goes to a human.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from app.config import FLOOR, GATE, MARGIN, gate_for

Outcome = Literal["advise", "clarify", "escalate", "retake"]
"""'retake' is only for a photo that is not a crop at all — an expert's time is
the scarcest thing in the system and should not be spent on a blurry shoe."""


@dataclass(frozen=True)
class Prediction:
    target: str
    confidence: float


@dataclass(frozen=True)
class TopK:
    predictions: list[Prediction]
    """Descending by confidence, at least two entries."""
    model_version: str
    is_stub: bool
    out_of_scope: bool = False
    oos_reason: str | None = None
    heatmap: dict | None = None
    prior_bias: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class GateDecision:
    outcome: Outcome
    reason: str
    confidence: float
    threshold: float
    alternatives: list[Prediction]
    cue_id: str | None = None


def crop_of(target: str) -> str:
    return target.split("_", 1)[0]


def is_healthy(target: str) -> bool:
    return target.endswith("_healthy")


def threshold_of(reason: str, top_target: str | None) -> float:
    """The bar a stored decision was judged against, from its reason — so a
    past result can be shown again (in another language) with the same meter."""
    if reason == "BELOW_FLOOR":
        return FLOOR
    if reason in ("AMBIGUOUS", "AMBIGUOUS_NO_CUE"):
        return MARGIN
    if reason in ("LAB_CLASS_CONFIRM", "LAB_CLASS_BELOW_GATE") and top_target:
        return gate_for(top_target)
    if reason == "CROP_NOT_SUPPORTED":
        return 0.0
    return GATE


def decide(
    topk: TopK,
    *,
    farm_crop: str,
    tier_of: Callable[[str], str | None],
    has_advisory: Callable[[str], bool],
    cue_for: Callable[[str, str], dict | None],
) -> GateDecision:
    preds = topk.predictions
    top1 = preds[0]
    top2 = preds[1] if len(preds) > 1 else Prediction(top1.target, 0.0)
    alts = list(preds)

    def out(outcome: Outcome, reason: str, threshold: float, cue_id: str | None = None):
        return GateDecision(outcome, reason, top1.confidence, threshold, alts, cue_id)

    if topk.out_of_scope:
        if topk.oos_reason == "NOT_A_CROP_PHOTO":
            return out("retake", "NOT_A_CROP_PHOTO", GATE)
        return out("escalate", topk.oos_reason or "OUT_OF_SCOPE", GATE)

    if crop_of(top1.target) != farm_crop:
        return out("escalate", "CROP_MISMATCH", GATE)

    if top1.confidence < FLOOR:
        return out("escalate", "BELOW_FLOOR", FLOOR)

    if top1.confidence - top2.confidence < MARGIN:
        cue = cue_for(top1.target, top2.target)
        if cue is None:
            return out("escalate", "AMBIGUOUS_NO_CUE", MARGIN)
        return out("clarify", "AMBIGUOUS", MARGIN, cue["id"])

    if top1.confidence < GATE:
        return out("escalate", "BELOW_GATE", GATE)

    bar = gate_for(top1.target)
    if top1.confidence < bar:  # a lab-trained class, between the global gate and its own
        cue = cue_for(top1.target, top2.target)
        if cue is not None:
            return out("clarify", "LAB_CLASS_CONFIRM", bar, cue["id"])
        return out("escalate", "LAB_CLASS_BELOW_GATE", bar)

    if is_healthy(top1.target):
        return out("advise", "HEALTHY", GATE)

    if tier_of(top1.target) != "diagnosable":
        return out("escalate", "NOT_PHOTO_DIAGNOSABLE", GATE)

    if not has_advisory(top1.target):
        return out("escalate", "NO_KB_ENTRY", GATE)

    return out("advise", "ABOVE_GATE", GATE)
