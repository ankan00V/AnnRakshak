"""Expert verdicts -> training data. Every case an agronomist confirmed or
corrected is a field photo from a farmer's phone with a trustworthy label —
the data the model most lacks. This exports them for the next training run.

    .venv/bin/python ml/export_confirmed.py
      -> data/processed/confirmed/<class>/*.jpg, data/processed/confirmed.csv
    .venv/bin/python ml/train.py --with-extra --warm-start --with-confirmed

The label is the expert's final label (a correction overrides the model).
Targets the model has no class for (inspection-tier pests) are counted, not
exported. A retrained model still goes live only through train.py's
deploy-if-not-worse gate.

Two kinds of photo are left out, both found in a real export (18 Nov 2026,
8 and 10 of 26). A photo that is one the model is tested on: the team checks
the app with photos from the datasets, and one of those confirmed and trained
on is a test answer learnt by heart, which flatters every score after it. And
a photo confirmed twice — the same upload checked again — which would count
once in the data and twice in the weights. Both by perceptual hash (dHash,
Hamming <= 4), against ml/artifacts/split.json's held-out photos and against
what this export has already taken.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "data"))

from sqlalchemy import select  # noqa: E402

from app.config import UPLOAD_DIR  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Confirmation, Diagnosis, Farm, Problem  # noqa: E402
from ingest_more import dhash, near  # noqa: E402
from PIL import Image  # noqa: E402

ART = ROOT / "ml" / "artifacts"
OUT = ROOT / "data" / "processed" / "confirmed"
MANIFEST = ROOT / "data" / "processed" / "confirmed.csv"


def class_for(target: str, classes: list[str], c2t: dict[str, str]) -> str | None:
    """The training class for an expert's label; a target split into several
    classes (leaf and neck blast) goes to the one named like it, else the first."""
    matches = [c for c in classes if c2t[c] == target]
    if not matches:
        return None
    return target if target in matches else matches[0]


def main() -> None:
    meta = json.loads((ART / "meta.json").read_text())
    classes, c2t = meta["classes"], meta["class_to_target"]
    split = json.loads((ART / "split.json").read_text())
    held_out = []
    for p in split["test"] + split.get("extra_test", []):
        with Image.open(ROOT / p) as im:
            held_out.append(dhash(im))
    taken: list[int] = []
    rows, skipped = [], Counter()
    shutil.rmtree(OUT, ignore_errors=True)  # an earlier export's leftovers would not be in this manifest
    with SessionLocal() as db:
        for conf in db.scalars(select(Confirmation).order_by(Confirmation.id)).all():
            problem = db.get(Problem, conf.problem_id)
            farm = db.get(Farm, problem.farm_id) if problem else None
            cls = class_for(conf.final_label, classes, c2t)
            if cls is None:
                skipped[f"no photo class for {conf.final_label}"] += 1
                continue
            diags = db.scalars(select(Diagnosis).where(Diagnosis.problem_id == conf.problem_id,
                                                        Diagnosis.image_path.is_not(None))).all()
            for d in diags:
                src = UPLOAD_DIR / d.image_path
                if not src.exists():
                    skipped["image file missing on this server"] += 1
                    continue
                with Image.open(src) as im:
                    h = dhash(im)
                if near(h, held_out, 4):
                    skipped["a held-out test photo"] += 1
                    continue
                if near(h, taken, 4):
                    skipped["the same photo confirmed again"] += 1
                    continue
                taken.append(h)
                dst = OUT / cls / f"c{conf.id}_d{d.id}.jpg"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                rows.append({"path": str(dst.relative_to(ROOT)), "train_class": cls, "target": conf.final_label,
                             "crop": cls.split("_")[0], "source": "confirmed", "bg": "field",
                             "verdict": conf.verdict, "model_label": conf.model_label or "",
                             "district": farm.district if farm else "", "confirmed_at": conf.created_at.isoformat()})
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["path"])
        w.writeheader()
        w.writerows(rows)
    by = Counter((r["train_class"], r["verdict"]) for r in rows)
    print(f"exported {len(rows)} expert-labelled field photos -> {MANIFEST.relative_to(ROOT)}")
    for (c, v), n in sorted(by.items()):
        print(f"  {c:32s} {v:9s} {n}")
    for why, n in skipped.items():
        print(f"  skipped {n}: {why}")


if __name__ == "__main__":
    main()
