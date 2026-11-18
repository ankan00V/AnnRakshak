"""Hugging Face image sets for the classes still short of photographs.

Read through the Hub's dataset viewer API, a page of rows at a time, keeping
only the labels mapped below; every other label is never downloaded. Each
image is de-duplicated against everything already in data/processed (dHash,
Hamming <= 3) and within this import (<= 4), so a set that mirrors one we
already have adds nothing — which is the expected result for several of them,
and the point of checking.

Mapped, and why:
  AlvaroVasquezAI/Maize_Leaf_Diseases   northern leaf blight is turcicum;
                                        ours are mostly lab shots. Gray leaf spot.
  muAtarist/maize_foliar_diseases       gray leaf spot ("CornLeafBlight" is not
  InriaXagriscienceFM/maize_corn_...    said which blight, so it is left)
  Project-AgML/cotton_disease_classification   Alternaria, our thinnest cotton
  Project-AgML/cotton_leaf_disease_classification  disease (161 photos)
  Project-AgML/cotton_leaf_disease_classification_bangladesh_2  jassid, herbicide
                                        damage, leaf reddening
  sairiamu/maize_desease_dataset        maize ear rot and fall armyworm (its
                                        nutrient-deficiency labels are not ours)
  Ashmita2000/Cotton_Leaves             cotton aphids
Left out on purpose: labels that do not say which disease ("Corn Leaf Blight",
"Insects damage", "bad"/"good"), and insect-portrait sets (CT_PestNet): our
pest classes mean the damage a farmer's phone sees, not the insect posed.

    .venv/bin/python data/ingest_hf.py        (HF_TOKEN read from .env)
      -> data/processed/hf_640/<class>/*.jpg, data/processed/hf_images.csv
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv  # noqa: PLC0415

    load_dotenv(ROOT / ".env")
except ImportError:
    pass
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "data"))
from composite import is_plain  # noqa: E402
from ingest_more import dhash, near  # noqa: E402

VIEWER = "https://datasets-server.huggingface.co"
OUT = ROOT / "data" / "processed" / "hf_640"
CSV_OUT = ROOT / "data" / "processed" / "hf_images.csv"
EXISTING = [p for p in (ROOT / "data" / "processed").glob("*_640") if p.name != "hf_640"]
LONG_SIDE = 640
FIELDS = ["path", "train_class", "target", "crop", "source", "bg", "dhash"]

# dataset -> {label name: (training class, KB target, crop)}
MAP = {
    "AlvaroVasquezAI/Maize_Leaf_Diseases": {
        "Northern_Leaf_Blight": ("maize_turcicum_leaf_blight", "maize_turcicum_leaf_blight", "maize"),
        "Gray_Leaf_Spot": ("maize_gray_leaf_spot", "maize_gray_leaf_spot", "maize"),
    },
    "muAtarist/maize_foliar_diseases": {
        "GreyLeafSpot": ("maize_gray_leaf_spot", "maize_gray_leaf_spot", "maize"),
    },
    "InriaXagriscienceFM/maize_corn_corn_leaf_disease_detection": {
        "Gray Leaf Spot": ("maize_gray_leaf_spot", "maize_gray_leaf_spot", "maize"),
    },
    "Project-AgML/cotton_disease_classification": {
        "Alternaria": ("cotton_alternaria_leaf_spot", "cotton_alternaria_leaf_spot", "cotton"),
    },
    "Project-AgML/cotton_leaf_disease_classification": {
        "Alternaria_Leaf": ("cotton_alternaria_leaf_spot", "cotton_alternaria_leaf_spot", "cotton"),
    },
    "Project-AgML/cotton_leaf_disease_classification_bangladesh_2": {
        "Leaf Hopper Jassids": ("cotton_jassid", "cotton_jassid", "cotton"),
        "Herbicide Growth Damage": ("cotton_herbicide_damage", "cotton_herbicide_damage", "cotton"),
        "Leaf Redding": ("cotton_leaf_reddening", "cotton_leaf_reddening", "cotton"),
    },
    "sairiamu/maize_desease_dataset": {
        "maize ear rot": ("maize_ear_rot", "maize_ear_rot", "maize"),
        "maize fall armyworm": ("maize_fall_armyworm", "maize_fall_armyworm", "maize"),
    },
    "Ashmita2000/Cotton_Leaves": {
        "Aphids edited": ("cotton_aphid", "cotton_aphid", "cotton"),
    },
}


def _get(url: str, binary: bool = False):
    headers = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"} if os.environ.get("HF_TOKEN") else {}
    for attempt in range(10):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as r:
                data = r.read()
            return data if binary else json.loads(data)
        except Exception:  # noqa: BLE001  the viewer rate-limits: back off and retry
            time.sleep(2 + 3 * attempt)
    raise OSError(f"could not fetch {url[:120]}")


def rows(dataset: str):
    """(label name, image URL) for every row whose label is mapped."""
    info = _get(f"{VIEWER}/info?" + urllib.parse.urlencode({"dataset": dataset}))["dataset_info"]
    # A dataset whose only configuration is unnamed reports it as ''; the rows
    # endpoint wants the name the splits endpoint gives it.
    named = {s["config"] for s in _get(f"{VIEWER}/splits?" + urllib.parse.urlencode({"dataset": dataset}))["splits"]}
    for key, cfg in info.items():
        if "augment" in key.lower():
            continue  # generated copies of the raw photos: they teach nothing and leak into the test split
        config = key if key in named else next(iter(named))
        names = cfg["features"]["label"].get("names") or []
        wanted = {i for i, n in enumerate(names) if n in MAP[dataset]}
        for split, s in cfg.get("splits", {}).items():
            for offset in range(0, s["num_examples"], 100):
                page = _get(f"{VIEWER}/rows?" + urllib.parse.urlencode(
                    {"dataset": dataset, "config": config, "split": split, "offset": offset, "length": 100}))
                for r in page.get("rows", []):
                    row = r["row"]
                    if row.get("label") in wanted and isinstance(row.get("image"), dict):
                        yield names[row["label"]], row["image"]["src"]


def _load_done() -> list[dict[str, str]]:
    """The rows already written, or — after a run that stopped before writing
    its index — the photos it left on disk, read back."""
    if CSV_OUT.exists():
        with CSV_OUT.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))
    by_prefix = {d.split("/")[0][:16]: d for d in MAP}
    crop_of = {cls: crop for m in MAP.values() for cls, _, crop in m.values()}
    out = []
    for p in sorted(OUT.rglob("*.jpg")):
        dataset = by_prefix.get(p.stem.split("_", 1)[1]) if "_" in p.stem else None
        if not dataset:
            continue
        with Image.open(p) as im:
            out.append({"path": str(p.relative_to(ROOT)), "train_class": p.parent.name, "target": p.parent.name,
                        "crop": crop_of[p.parent.name], "source": f"hf:{dataset}",
                        "bg": "plain" if is_plain(im.convert("RGB")) else "field", "dhash": f"{dhash(im):016x}"})
    return out


def _write(rows: list[dict[str, str]]) -> None:
    with CSV_OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    known: set[int] = set()
    for d in EXISTING:
        for p in d.rglob("*.jpg"):
            with Image.open(p) as im:
                known.add(dhash(im))
    known_list = list(known)
    print(f"{len(known)} images already in data/processed", flush=True)

    out_rows = _load_done()
    seen: list[int] = [int(r["dhash"], 16) for r in out_rows]
    done = {r["source"].removeprefix("hf:") for r in out_rows}
    _write(out_rows)
    print(f"{len(out_rows)} photos already imported from {sorted(done) or 'nothing'}", flush=True)
    for dataset in MAP:
        if dataset in done:
            continue
        stats: Counter[str] = Counter()
        try:
            batch = list(rows(dataset))
        except OSError as exc:  # one set the viewer cannot serve does not stop the others
            print(f"  {dataset}: skipped ({exc})", flush=True)
            continue
        for label, src in batch:
            cls, target, crop = MAP[dataset][label]
            try:
                im = ImageOps.exif_transpose(Image.open(io.BytesIO(_get(src, binary=True)))).convert("RGB")
            except Exception:  # noqa: BLE001
                stats["unreadable"] += 1
                continue
            h = dhash(im)
            if h in known or near(h, known_list, 3) or near(h, seen, 4):
                stats[f"duplicate {cls}"] += 1
                continue
            seen.append(h)
            im.thumbnail((LONG_SIDE, LONG_SIDE))
            dst = OUT / cls / f"{len(seen):05d}_{dataset.split('/')[0][:16]}.jpg"
            while dst.exists():
                dst = dst.with_name(f"{dst.stem}b.jpg")
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst, "JPEG", quality=88)
            out_rows.append({"path": str(dst.relative_to(ROOT)), "train_class": cls, "target": target,
                             "crop": crop, "source": f"hf:{dataset}", "bg": "plain" if is_plain(im) else "field",
                             "dhash": f"{h:016x}"})
            stats[f"kept {cls}"] += 1
        print(f"  {dataset}: {dict(stats)}", flush=True)
        _write(out_rows)

    print(f"wrote {CSV_OUT.relative_to(ROOT)}: {len(out_rows)} new images  "
          f"{dict(Counter(r['train_class'] for r in out_rows))}")


if __name__ == "__main__":
    main()
