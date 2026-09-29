"""Dhan-Shomadhan: Bangladeshi rice, and the sheath blight photographs we lacked.

Sheath blight had 50 images, all ICAR, and it is one of the handful of ~50-image
classes that cost the 29 Sep candidate its last deploy check. This set carries
285 of them, shot in two deliberate ways — on the plant in the field, and on a
white sheet — which is the split background randomisation is built for.

The folder names are misspelt in the archive, and inconsistently: sheath blight
arrives as both "Shath Blight" and "Sheath Blight", tungro as "Rice Tungro" and
"Rice Turgro", brown spot as "Brown Spot" and "Browon Spot". They are mapped by
hand below rather than by matching text, so a typo cannot quietly drop a class.

Leaf scald (219 photos) is left out: the app has no advisory for it, and the
rule here is that the model never names a problem the app cannot then explain.

    .venv/bin/python data/ingest_dhan.py
      -> data/processed/dhan_640/<class>/*.jpg
         data/processed/dhan_images.csv
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

ZIP = ROOT / "data" / "raw" / "dhan" / "dhan_shomadhan.zip"
OUT = ROOT / "data" / "processed" / "dhan_640"
CSV_OUT = ROOT / "data" / "processed" / "dhan_images.csv"
EXISTING = [ROOT / "data" / "processed" / d for d in
            ("icar_640", "extra_640", "more_640", "paddy_640", "asdid_640",
             "local_640", "cotton_640", "pests_640")]
LONG_SIDE = 640
SOURCE = "dhan_shomadhan"
FIELDS = ["path", "train_class", "target", "crop", "source", "bg", "dhash"]

# folder in the archive (as spelt there) -> (our class, our target)
USE = {
    "Shath Blight": ("rice_sheath_blight", "rice_sheath_blight"),
    "Sheath Blight": ("rice_sheath_blight", "rice_sheath_blight"),
    "Rice Blast": ("rice_leaf_blast", "rice_blast"),
    "Rice Tungro": ("rice_tungro", "rice_tungro"),
    "Rice Turgro": ("rice_tungro", "rice_tungro"),
    "Brown Spot": ("rice_brown_spot", "rice_brown_spot"),
    "Browon Spot": ("rice_brown_spot", "rice_brown_spot"),
    # "Leaf Scaled": no advisory in backend/kb, so the model must not learn to name it
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
                stats[f"skipped {folder}"] += 1
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
            if i % 300 == 0:
                print(f"  {i}/{len(names)} read", flush=True)

    with CSV_OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {CSV_OUT.relative_to(ROOT)}: {len(rows)} images")
    kept = Counter(r["train_class"] for r in rows)
    field = Counter(r["train_class"] for r in rows if r["bg"] == "field")
    for cls in sorted(kept):
        print(f"  {cls:28s} {kept[cls]:5d}  ({field[cls]} field)")
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(stats.items()) if not k.startswith("skipped")))


if __name__ == "__main__":
    main()
