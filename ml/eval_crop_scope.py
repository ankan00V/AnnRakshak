"""How the deployed model does when it only has to choose within the farm's crop.

The app always knows the farm's crop, yet the model picks among every class of
every crop and a top guess from another crop sends the photo to an expert.
This scores the held-out test photos (ml/artifacts/split.json: ICAR test and
the extra/more test rows) two ways:

  all      the top class over all crops (today)
  in-crop  the top class among the photo's own crop, and how much of the
           probability the model put on that crop at all

    ../.venv/bin/python ml/eval_crop_scope.py            (from the repo root: .venv/bin/python ml/eval_crop_scope.py)
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.engine.model import Classifier  # noqa: E402

ART = ROOT / "ml" / "artifacts"
MANIFESTS = ["icar_images.csv", "extra_images.csv", "more_images.csv"]


def labels() -> dict[str, str]:
    out = {}
    for name in MANIFESTS:
        for r in csv.DictReader(open(ROOT / "data" / "processed" / name)):
            out[r["path"]] = r["train_class"]
    return out


def main() -> None:
    clf = Classifier(ART)
    split = json.loads((ART / "split.json").read_text())
    truth = labels()
    rows = [(p, truth[p]) for p in split["test"] + split["extra_test"] if p in truth]
    classes = clf.classes
    target = clf.class_to_target
    crop_of = {c: c.split("_", 1)[0] for c in classes}
    idx_by_crop = defaultdict(list)
    for i, c in enumerate(classes):
        idx_by_crop[crop_of[c]].append(i)

    per = defaultdict(lambda: {"n": 0, "all": 0, "crop": 0, "mass": []})
    for path, cls in rows:
        img = Image.open(ROOT / path).convert("RGB")
        x = clf.tf(img).unsqueeze(0)
        with torch.no_grad():
            logits = clf.model(x)[0] / clf.temperature
        probs = torch.softmax(logits, dim=0).numpy()
        crop = crop_of[cls]
        own = idx_by_crop[crop]
        top_all = classes[int(np.argmax(probs))]
        top_in = classes[own[int(np.argmax(probs[own]))]]
        s = per[cls]
        s["n"] += 1
        s["all"] += target[top_all] == target[cls]
        s["crop"] += target[top_in] == target[cls]
        s["mass"].append(float(probs[own].sum()))

    print(f"{'class':34s} {'n':>4s} {'all-crops':>9s} {'in-crop':>8s} {'own-crop mass (median)':>24s}")
    tot = defaultdict(int)
    for cls in sorted(per):
        s = per[cls]
        tot["n"] += s["n"]; tot["all"] += s["all"]; tot["crop"] += s["crop"]
        print(f"{cls:34s} {s['n']:4d} {s['all'] / s['n']:9.3f} {s['crop'] / s['n']:8.3f} {np.median(s['mass']):24.3f}")
    print(f"{'ALL':34s} {tot['n']:4d} {tot['all'] / tot['n']:9.3f} {tot['crop'] / tot['n']:8.3f}")
    for crop in sorted(idx_by_crop):
        n = sum(per[c]["n"] for c in per if crop_of[c] == crop)
        a = sum(per[c]["all"] for c in per if crop_of[c] == crop)
        b = sum(per[c]["crop"] for c in per if crop_of[c] == crop)
        if n:
            print(f"  {crop:10s} n={n:4d}  all-crops {a / n:.3f}  in-crop {b / n:.3f}")


if __name__ == "__main__":
    main()
