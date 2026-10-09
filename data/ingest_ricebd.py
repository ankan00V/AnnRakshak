"""Rice Leaf Bacterial and Fungal Disease Dataset — Sirajganj and Pabna, 2023.

1,701 photographs taken over four months in Bangladeshi fields, indoor and
outdoor light. It is here for one class above all: sheath blight, which had 50
images in this repo and is one of the ~50-image classes that cost the 29 Sep
candidate its last deploy check. With this and Dhan-Shomadhan it passes 500.

Two of its eight folders are not imported:

  Leaf scald              234 photos, and backend/kb has no advisory for it
  Narrow brown leaf spot  166, same

Both are real rice diseases and both occur in India; neither is something this
app can currently explain, and a model that names a problem the app cannot
answer sends a farmer away with a word and no help. They are worth an advisory
and a later import, in that order.

The archive ships its own train/test/validation split. It is ignored: this
repo makes its own split per class, and the de-duplication here runs across the
whole set so a photograph cannot sit on both sides of ours.

    .venv/bin/python data/ingest_ricebd.py
      -> data/processed/ricebd_640/<class>/*.jpg
         data/processed/ricebd_images.csv
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "data"))
from composite import is_plain  # noqa: E402
from ingest_more import dhash, near  # noqa: E402

ZIP = (ROOT / "data" / "raw" / "rice_bd_fungal" /
       "Rice Leaf Bacterial and Fungal Disease Dataset" / "Rice leaf disease.zip")
OUT = ROOT / "data" / "processed" / "ricebd_640"
CSV_OUT = ROOT / "data" / "processed" / "ricebd_images.csv"
EXISTING = [ROOT / "data" / "processed" / d for d in
            ("icar_640", "extra_640", "more_640", "paddy_640", "asdid_640",
             "local_640", "cotton_640", "pests_640", "dhan_640")]
LONG_SIDE = 640
SOURCE = "rice_bd_fungal"
FIELDS = ["path", "train_class", "target", "crop", "source", "bg", "dhash"]

USE = {
    "Sheath Blight": ("rice_sheath_blight", "rice_sheath_blight"),
    "Leaf Blast": ("rice_leaf_blast", "rice_blast"),
    "Brown Spot": ("rice_brown_spot", "rice_brown_spot"),
    "Rice Hispa": ("rice_hispa", "rice_hispa"),
    "Bacterial Leaf Blight": ("rice_bacterial_leaf_blight", "rice_bacterial_leaf_blight"),
    "Healthy Rice Leaf": ("rice_healthy", "rice_healthy"),
}


def main() -> None:
    if not ZIP.exists():
        raise SystemExit(f"missing {ZIP.relative_to(ROOT)}")
    known: set[int] = set()
    for d in EXISTING:
        for p in d.rglob("*.jpg"):
            with Image.open(p) as im:
                known.add(dhash(im))
    known_list = list(known)
    print(f"{len(known)} images already in data/processed", flush=True)

    rows: list[dict[str, str]] = []
    seen: dict[str, list[int]] = {}
    stats: Counter[str] = Counter()
    with zipfile.ZipFile(ZIP) as zf:
        names = sorted(n for n in zf.namelist() if n.lower().endswith((".jpg", ".jpeg", ".png")))
        for i, name in enumerate(names, 1):
            folder = Path(name).parent.name
            if folder not in USE:
                stats[f"no advisory: {folder}"] += 1
                continue
            cls, target = USE[folder]
            try:
                im = ImageOps.exif_transpose(Image.open(io.BytesIO(zf.read(name)))).convert("RGB")
            except Exception:  # noqa: BLE001  unreadable file
                stats["unreadable"] += 1
                continue
            h = dhash(im)
            pool = seen.setdefault(cls, [])
            if h in known or near(h, known_list, 3) or near(h, pool):
                stats["duplicate"] += 1
                continue
            pool.append(h)
            im.thumbnail((LONG_SIDE, LONG_SIDE))
            dst = OUT / cls / f"{len(pool):05d}_{Path(name).stem[:34]}.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst, "JPEG", quality=88)
            rows.append({"path": str(dst.relative_to(ROOT)), "train_class": cls, "target": target,
                         "crop": "rice", "source": SOURCE, "bg": "plain" if is_plain(im) else "field",
                         "dhash": f"{h:016x}"})
            stats["kept"] += 1
            if i % 400 == 0:
                print(f"  {i}/{len(names)} read", flush=True)

    with CSV_OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {CSV_OUT.relative_to(ROOT)}: {len(rows)} images")
    kept = Counter(r["train_class"] for r in rows)
    field = Counter(r["train_class"] for r in rows if r["bg"] == "field")
    for cls in sorted(kept):
        print(f"  {cls:30s} {kept[cls]:5d}  ({field[cls]} field)")
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(stats.items())))


if __name__ == "__main__":
    main()
