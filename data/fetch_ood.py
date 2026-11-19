"""Plant photos that are not our crops, for testing the photo checks.

The familiarity check (ml/build_familiarity.py) and the closer look the app
takes at a wide photo (backend/app/engine/vision.py) must both turn away a
leaf the app knows nothing about. A photo of a face or a room is easy to
turn away. A bean leaf with spots is not, and that is the photo these
checks are tested on. None of this is trained on.

  AI-Lab-Makerere/beans                    bean leaves, phone photos, Ugandan fields
  Project-AgML/rangeland_weeds_australia   DeepWeeds: weeds in the field, Queensland
  Project-AgML/plant_village_classification  PlantVillage, every crop except
                                           maize and soybean (ours)

    .venv/bin/python data/fetch_ood.py        (HF_TOKEN read from .env)
      -> data/raw/ood_plants/<set>/*.jpg
"""

from __future__ import annotations

import io
import random
import sys
import urllib.parse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
from ingest_hf import VIEWER, _get  # noqa: E402

OUT = ROOT / "data" / "raw" / "ood_plants"
PER_SET = 200
SETS = {
    "beans": ("AI-Lab-Makerere/beans", "labels", None),
    "weeds": ("Project-AgML/rangeland_weeds_australia", "label", None),
    # PlantVillage's own maize and soybean classes are crops the app knows
    "plantvillage": ("Project-AgML/plant_village_classification", "label", ("corn", "maize", "soybean")),
}


def fetch(name: str, dataset: str, label_key: str, skip: tuple[str, ...] | None) -> None:
    dst = OUT / name
    dst.mkdir(parents=True, exist_ok=True)
    have = len(list(dst.glob("*.jpg")))
    if have >= PER_SET:
        print(f"{name}: {have} already")
        return
    info = _get(f"{VIEWER}/info?" + urllib.parse.urlencode({"dataset": dataset}))["dataset_info"]
    cfg = next(iter(info.values()))
    names = cfg["features"].get(label_key, {}).get("names") or []
    split, s = next(iter(cfg["splits"].items()))
    rng = random.Random(11)
    offsets = sorted(rng.sample(range(0, s["num_examples"] - 10), 60))
    n = have
    for off in offsets:
        if n >= PER_SET:
            break
        page = _get(f"{VIEWER}/rows?" + urllib.parse.urlencode(
            {"dataset": dataset, "config": "default", "split": split, "offset": off, "length": 5}))
        for r in page.get("rows", []):
            row = r["row"]
            lab = row.get(label_key)
            lab_name = names[lab] if isinstance(lab, int) and lab < len(names) else str(lab)
            if skip and any(w in lab_name.lower() for w in skip):
                continue
            img = row.get("image")
            if not isinstance(img, dict):
                continue
            im = Image.open(io.BytesIO(_get(img["src"], binary=True))).convert("RGB")
            im.thumbnail((640, 640))
            im.save(dst / f"{n:04d}.jpg", "JPEG", quality=90)
            n += 1
            if n >= PER_SET:
                break
    print(f"{name}: {n} photos")


def main() -> None:
    for name, (dataset, key, skip) in SETS.items():
        fetch(name, dataset, key, skip)


if __name__ == "__main__":
    main()
