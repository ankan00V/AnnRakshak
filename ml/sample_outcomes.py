"""Run every held-out TEST photo through the production pipeline (vegetation
check → deployed classifier → confidence gate, no district prior) and record
what the app will do with it.

    .venv/bin/python ml/sample_outcomes.py

Writes ml/artifacts/sample_outcomes.json. /api/samples uses it to tag demo
photos with the path they take — so a presenter can pick the photo that makes
the Doubt Doctor ask its question, instead of hoping for one.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine import gate, vision  # noqa: E402
from app.kb import get_kb  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from holdout import target_of  # noqa: E402


def main() -> None:
    if vision.model_status()["is_stub"]:
        sys.exit("No trained model in ml/artifacts — run ml/train.py first.")
    kb = get_kb()
    meta = json.loads((vision.ARTIFACTS / "meta.json").read_text())
    c2t = meta["class_to_target"]
    sp = json.loads((vision.ARTIFACTS / "split.json").read_text())
    test = sp["test"] + sp.get("extra_test", [])  # extra: blast, rust, field FAW (v2 models)

    out: dict[str, dict] = {}
    tally = Counter()
    skipped = Counter()
    for path in test:
        cls = path.split("/")[-2]
        truth = target_of(cls, c2t)
        if truth is None:          # a folder this model has no target for
            skipped[cls] += 1
            continue
        crop = cls.split("_")[0]
        topk = vision.classify((ROOT / path).read_bytes(), crop)
        d = gate.decide(
            topk,
            farm_crop=crop,
            tier_of=lambda t: kb.targets.get(t, {}).get("tier"),
            has_advisory=lambda t: t in kb.advisories,
            cue_for=kb.cue_for,
        )
        top = topk.predictions[0].target if topk.predictions else None
        correct = top == truth
        key = "/".join(path.split("/")[-2:])
        out[key] = {"outcome": d.outcome, "reason": d.reason, "top": top,
                    "confidence": round(d.confidence, 3), "top_correct": correct}
        tally[d.outcome] += 1
        if d.outcome == "advise":
            tally["advise_correct" if correct else "advise_wrong"] += 1

    dest = vision.ARTIFACTS / "sample_outcomes.json"
    dest.write_text(json.dumps({"model_version": meta["model_version"], "samples": out}, indent=1))
    for cls, n in skipped.items():
        print(f"skipped {cls}: {n} photos, no target in this model")
    print(f"{len(out)} test photos → {dict(tally)}\nwrote {dest}")
    for k, v in out.items():
        if v["outcome"] == "clarify":
            print(f"  clarify: {k}  top={v['top']}  conf={v['confidence']}")


if __name__ == "__main__":
    main()
