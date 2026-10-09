"""Rice leaf folder photos, from a pest set whose other folders we do not use.

The 29 Sep candidate failed its last deploy check on four photos, and two of
them were the same class: rice leaf folder called something else, once as white
stem borer at 0.95 confidence. Leaf folder had 49 photographs, all from ICAR,
inside a model that by then carried 46 classes and 47,000 images. A class that
thin cannot hold its ground.

The set (Mendeley y5hwbhrn5m, paddy field pests, Bangladesh) was looked at once
before and turned down whole, on the strength of its brown planthopper folder:
reference macro shots of the insect, several of them near-duplicate crops of
one photograph, nothing like what a farmer's phone sends. That judgement was
right for that folder and wrong as a judgement of the set.

  LEAF_FOLDERS   166 photos, and most of them show the damage — the rolled leaf,
                 the white scraped streaks along the blade, the caterpillar in
                 place. That is the signature the app names. Taken.
  Stemz_Borer    172 photos, and all of them are adult moths, posed. Our stem
                 borer classes are about dead hearts and white ears, and a moth
                 portrait would teach the class the wrong thing. Left.
  the rest       green leafhopper, rice bug, whorl maggot, brown planthopper:
                 not targets the app advises on, and the same macro framing.

    .venv/bin/python data/ingest_pests.py
      -> data/processed/pests_640/rice_leaf_folder/*.jpg
         data/processed/pests_images.csv
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

INNER = ROOT / "data" / "raw" / "pests_mendeley" / "New folder (4)" / "original_data-20250714T051407Z-1-001.zip"
OUT = ROOT / "data" / "processed" / "pests_640"
CSV_OUT = ROOT / "data" / "processed" / "pests_images.csv"
EXISTING = [ROOT / "data" / "processed" / d for d in
            ("icar_640", "extra_640", "more_640", "paddy_640", "asdid_640", "local_640", "cotton_640")]
LONG_SIDE = 640
SOURCE = "paddy_pests"
USE = {"LEAF_FOLDERS": ("rice_leaf_folder", "rice_leaf_folder")}
FIELDS = ["path", "train_class", "target", "crop", "source", "bg", "dhash"]


def main() -> None:
    if not INNER.exists():
        raise SystemExit(f"missing {INNER.relative_to(ROOT)}")
    known: set[int] = set()
    for d in EXISTING:
        for p in d.rglob("*.jpg"):
            with Image.open(p) as im:
                known.add(dhash(im))
    known_list = list(known)
    print(f"{len(known)} images already in data/processed", flush=True)

    rows: list[dict[str, str]] = []
    seen: list[int] = []
    stats: Counter[str] = Counter()
    with zipfile.ZipFile(INNER) as zf:
        for name in sorted(zf.namelist()):
            folder = Path(name).parent.name
            if folder not in USE or not name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            cls, target = USE[folder]
            try:
                im = ImageOps.exif_transpose(Image.open(io.BytesIO(zf.read(name)))).convert("RGB")
            except Exception:  # noqa: BLE001  unreadable file
                stats["unreadable"] += 1
                continue
            h = dhash(im)
            # a tighter bar within this set: it carries near-duplicate crops of
            # the same photograph, which would otherwise land in both splits
            if h in known or near(h, known_list, 3) or near(h, seen, 5):
                stats["duplicate"] += 1
                continue
            seen.append(h)
            im.thumbnail((LONG_SIDE, LONG_SIDE))
            dst = OUT / cls / f"{len(seen):05d}_{Path(name).stem[:34]}.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst, "JPEG", quality=88)
            rows.append({"path": str(dst.relative_to(ROOT)), "train_class": cls, "target": target,
                         "crop": "rice", "source": SOURCE, "bg": "plain" if is_plain(im) else "field",
                         "dhash": f"{h:016x}"})
            stats["kept"] += 1

    with CSV_OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    field = sum(1 for r in rows if r["bg"] == "field")
    print(f"wrote {CSV_OUT.relative_to(ROOT)}: {len(rows)} images ({field} field)  {dict(stats)}")


if __name__ == "__main__":
    main()
