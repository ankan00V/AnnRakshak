""""An India soyabean leaf dataset" (Mendeley bshkvgbzpt) -> 640 px copies.

    .venv/bin/python data/ingest_soyleaf.py "<An India soyabean leaf dataset.zip>"
      -> data/processed/more_640/soyleaf/<class>/*.jpg
         data/processed/soyleaf_images.csv

Indian soybean leaves photographed in the field on a phone, foldered by
disease. What it gives us, and what it does not:

  soybean_septoria_brown_spot  284 images — this one matters. Septoria recall is
                               0.681 against a 0.70 deploy bar, and it is one of
                               the three classes keeping cotton and soybean
                               photo diagnosis switched off. These are a second,
                               independent source for it (the existing ones come
                               from MH-SoyaHealthVision), which is worth more
                               than more photos from the same source would be.
  soybean_healthy              288 images.
  soybean_unlabelled           2,184 raw + 230 dry-leaf + 10 root photos, for the
                               familiarity bank only (ml/build_familiarity.py):
                               real Indian phone shots of soybean, which is what
                               that bank is short of.

Two folders are deliberately NOT trained on:
  6.Bacterial leaf Blight (226) and 2.Vein Necrosis (138) are real diseases we
  have no KB target or verified advisory for. Training a class the app cannot
  advise on would mean recognising a problem and then having nothing to say —
  they are recorded here as unlabelled so the work is not lost when those
  entries are written.
  3.Dry_leaf is senescence, not a diagnosis.
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
from ingest_soynet import Seen, dhash  # noqa: E402  same hashing, same tolerance

OUT = ROOT / "data" / "processed" / "more_640" / "soyleaf"
MANIFEST = ROOT / "data" / "processed" / "soyleaf_images.csv"
LONG_SIDE = 640
SOURCE = "soyleaf"

FOLDERS = {
    "/4.Septoria_Brown_Spot/": ("soybean_septoria_brown_spot", "train"),
    "/1.Healthy/": ("soybean_healthy", "train"),
    "/6.Bacterial leaf Blight/": ("soybean_unlabelled", "familiarity"),
    "/2.Vein Necrosis/": ("soybean_unlabelled", "familiarity"),
    "/3.Dry_leaf/": ("soybean_unlabelled", "familiarity"),
    "/Leaf Images All (Raw)/": ("soybean_unlabelled", "familiarity"),
}


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    zpath = Path(sys.argv[1]).expanduser()
    if not zpath.exists():
        sys.exit(f"no such archive: {zpath}")

    known: list[int] = []
    for name in ("more_images.csv", "soynet_images.csv"):
        p = ROOT / "data" / "processed" / name
        if p.exists():
            known += [int(r["dhash"], 16) for r in csv.DictReader(p.open())
                      if r.get("crop") == "soybean" and r.get("dhash")]
    print(f"{len(known)} soybean images already held; de-duplicating against them", flush=True)

    rows, seen, dropped = [], Seen(known), 0
    with zipfile.ZipFile(zpath) as z:
        members = [m for m in z.namelist() if not m.endswith("/")]
        for folder, (cls, use) in FOLDERS.items():
            picked = [m for m in members if folder in m]
            print(f"{folder} -> {cls} ({use}): {len(picked)} files", flush=True)
            dest = OUT / cls
            dest.mkdir(parents=True, exist_ok=True)
            for i, m in enumerate(picked):
                try:
                    with z.open(m) as f, Image.open(io.BytesIO(f.read())) as im:
                        im = im.convert("RGB")
                        h = dhash(im)
                        if seen.near(h):
                            dropped += 1
                            continue
                        seen.add(h)
                        im.thumbnail((LONG_SIDE, LONG_SIDE))
                        name = f"{cls}_{Path(m).stem}_{i}.jpg"
                        im.save(dest / name, quality=90)
                except (OSError, ValueError):
                    continue
                rows.append({"path": str((dest / name).relative_to(ROOT)), "train_class": cls,
                             "target": cls if use == "train" else "", "crop": "soybean",
                             "source": SOURCE, "bg": "field", "use": use, "dhash": f"{h:016x}"})
                if (i + 1) % 250 == 0:
                    print(f"  {i + 1}/{len(picked)}", flush=True)

    with MANIFEST.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "train_class", "target", "crop", "source", "bg", "use", "dhash"])
        w.writeheader()
        w.writerows(rows)
    kept: dict[str, int] = {}
    for r in rows:
        kept[r["train_class"]] = kept.get(r["train_class"], 0) + 1
    print(f"\nkept {len(rows)} images ({dropped} near-duplicates dropped) -> {MANIFEST}")
    for k, v in sorted(kept.items()):
        print(f"  {v:5d}  {k}")


if __name__ == "__main__":
    main()
