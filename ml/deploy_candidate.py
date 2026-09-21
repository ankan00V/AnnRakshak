"""Deploy a candidate model for some crops and not others.

    .venv/bin/python ml/deploy_candidate.py --crops rice,maize,cotton
    .venv/bin/python ml/deploy_candidate.py --rollback

ml/train.py deploys all or nothing: one failing check anywhere keeps the whole
candidate out. That is the right default, and it was too blunt for the
candidate trained on 17 Sep 2026. It beat the deployed model on the check the
app's promise rests on (ICAR accuracy-when-advised 0.9823 vs 0.9652) and passed
every rice, maize and cotton check, but soybean failed all four of its own. All
or nothing kept cotton farmers waiting on soybean's data.

This deploys per crop, with the same refusals made in code:

  - every ICAR check must have passed: those guard rice and maize, the crops
    the deployed model already serves, against getting worse;
  - every check for each crop being switched on must have passed;
  - photo diagnosis is switched ON for exactly those crops and OFF for every
    other crop — including any crop the candidate knows but failed on. A
    switched-off crop is never classified: its photos and live checks go to an
    expert (services.diagnose, live.new_session), and a switched-off crop
    predicted on another crop's field is a crop mismatch, also an expert.

The live model is copied to ml/artifacts/previous/ first; --rollback restores
it and the photo_diagnosis switches it ran with.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "ml" / "artifacts"
CAND = ART / "candidate"
PREV = ART / "previous"
CROPS = ROOT / "backend" / "kb" / "crops.json"
MODEL_FILES = ("model.pt", "meta.json", "split.json")
# Built for one model version; the classifier ignores a bank from another, so
# they are moved aside with the model rather than left to mislead.
DERIVED = ("familiarity_bank.npy", "familiarity.json", "sample_outcomes.json")


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def refusals(meta: dict, crops: list[str]) -> list[str]:
    """Why this candidate may not go live for these crops (empty = it may)."""
    checks = meta.get("deploy_checks") or []
    if not checks:
        return ["the candidate has no deploy checks recorded"]
    out = [f"ICAR check failed: {c['check']} ({c['value']})"
           for c in checks if c["check"].startswith("ICAR") and not c["passed"]]
    for crop in crops:
        if not any(cls.startswith(crop + "_") for cls in meta["classes"]):
            out.append(f"the candidate has no classes for {crop}")
        out += [f"{crop} check failed: {c['check']} ({c['value']})"
                for c in checks if c["check"].startswith(crop + "_") and not c["passed"]]
    return out


def set_photo_diagnosis(on: set[str]) -> dict[str, bool]:
    kb = load(CROPS)
    was = {c: v["photo_diagnosis"] for c, v in kb.items() if not c.startswith("_")}
    for crop, entry in kb.items():
        if not crop.startswith("_"):
            entry["photo_diagnosis"] = crop in on
    CROPS.write_text(json.dumps(kb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return was


def deploy(crops: list[str]) -> None:
    meta = load(CAND / "meta.json")
    why = refusals(meta, crops)
    if why:
        sys.exit("not deployed:\n  " + "\n  ".join(why))

    if PREV.exists():
        shutil.rmtree(PREV)
    PREV.mkdir(parents=True)
    for name in MODEL_FILES + DERIVED:
        if (ART / name).exists():
            shutil.move(str(ART / name), PREV / name)
    was = set_photo_diagnosis(set(crops))
    (PREV / "photo_diagnosis.json").write_text(json.dumps(was, indent=1) + "\n")

    for name in MODEL_FILES:
        shutil.copy2(CAND / name, ART / name)
    live = load(ART / "meta.json")
    live |= {"deployed": True, "deployed_at": datetime.now(UTC).isoformat(),
             "deployed_for_crops": sorted(crops),
             "deploy_note": "Per-crop deployment (ml/deploy_candidate.py): photo diagnosis is on only for "
                            "deployed_for_crops; the model's other classes are never served."}
    (ART / "meta.json").write_text(json.dumps(live, indent=1) + "\n")
    print(f"deployed {live['model_version']} for {', '.join(sorted(crops))}")
    print(f"photo_diagnosis now: {load_switches()}")
    print(f"previous model kept in {PREV.relative_to(ROOT)}; undo with --rollback")
    print("next: .venv/bin/python ml/build_familiarity.py, then restart the backend")


def load_switches() -> dict[str, bool]:
    return {c: v["photo_diagnosis"] for c, v in load(CROPS).items() if not c.startswith("_")}


def rollback() -> None:
    if not (PREV / "meta.json").exists():
        sys.exit("nothing to roll back to")
    for name in MODEL_FILES + DERIVED:
        if (ART / name).exists():
            (ART / name).unlink()
        if (PREV / name).exists():
            shutil.move(str(PREV / name), ART / name)
    was = load(PREV / "photo_diagnosis.json")
    kb = load(CROPS)
    for crop, on in was.items():
        kb[crop]["photo_diagnosis"] = on
    CROPS.write_text(json.dumps(kb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"rolled back to {load(ART / 'meta.json')['model_version']}; photo_diagnosis: {load_switches()}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", help="comma-separated crops to switch photo diagnosis on for")
    ap.add_argument("--rollback", action="store_true")
    ap.add_argument("--check", action="store_true", help="only say whether it would deploy")
    args = ap.parse_args()
    if args.rollback:
        return rollback()
    if not args.crops:
        sys.exit("--crops is required")
    crops = [c.strip() for c in args.crops.split(",") if c.strip()]
    if args.check:
        why = refusals(load(CAND / "meta.json"), crops)
        print("would deploy" if not why else "would refuse:\n  " + "\n  ".join(why))
        return
    deploy(crops)


if __name__ == "__main__":
    main()
