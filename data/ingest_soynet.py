"""SoyNet (Indian soybean, camera and mobile-phone photos) -> 640 px copies.

    .venv/bin/python data/ingest_soynet.py "<SoyNet ....zip>"
      -> data/processed/more_640/soynet/<class>/*.jpg
         data/processed/soynet_images.csv  (path, train_class, target, crop, source, bg, dhash)

What this set is, and what it is therefore used for. SoyNet labels its photos
only Disease_Pic vs Healthy_pic — one undifferentiated "diseased" bucket, no
rust/septoria/frogeye distinction, and the file names carry nothing either. So:

  soybean_healthy            445 real Indian healthy leaves — a training class.
  soybean_unlabelled         2,762 diseased + 448 mobile-phone photos with no
                             usable label. NEVER a training class: they go to
                             the familiarity bank (ml/build_familiarity.py),
                             which asks "is this the kind of photo I know?" and
                             needs no label at all. That is the part worth
                             having — 18% of held-out rice photos are currently
                             rejected as "not a crop photo" because the bank was
                             built from tight lab close-ups, and these are exactly
                             the wide phone shots it is missing.

Only Raw_SoyNet_Data is read. The Preprocessing_SoyNet_Data folders are
grayscale/resized/augmented derivatives of those same photos; training on them
would put copies of one leaf in both the training and the test split.

Reads members straight out of the zip and downscales as it goes, so the 9.3 GB
of originals is never written to disk.
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed" / "more_640" / "soynet"
MANIFEST = ROOT / "data" / "processed" / "soynet_images.csv"
LONG_SIDE = 640
SOURCE = "soynet"

# folder inside the archive -> (training class, what it may be used for)
FOLDERS = {
    "Raw_SoyNet_Data/Camera Clicks/Healthy_pic/": ("soybean_healthy", "train"),
    "Raw_SoyNet_Data/Camera Clicks/Disease_Pic/": ("soybean_unlabelled", "familiarity"),
    "Raw_SoyNet_Data/Mobile pic/": ("soybean_unlabelled", "familiarity"),
}


def dhash(im: Image.Image) -> int:
    g = np.asarray(im.convert("L").resize((9, 8), Image.BILINEAR), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def popcount(x: np.ndarray) -> np.ndarray:
    """Set bits per uint64, via the byte view — comparing one hash against
    20,000 others in a Python loop costs more than reading the image does."""
    return np.unpackbits(x.view(np.uint8)).reshape(-1, 64).sum(1)


class Seen:
    """The perceptual hashes held so far, as one array to compare against."""

    def __init__(self, hashes: list[int], tol: int = 4):
        self.arr = np.array(hashes, dtype=np.uint64)
        self.tol = tol

    def near(self, h: int) -> bool:
        if not len(self.arr):
            return False
        return bool((popcount(self.arr ^ np.uint64(h)) <= self.tol).any())

    def add(self, h: int) -> None:
        self.arr = np.append(self.arr, np.uint64(h))


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    zpath = Path(sys.argv[1]).expanduser()
    if not zpath.exists():
        sys.exit(f"no such archive: {zpath}")

    # data/ingest_more.py already recorded a perceptual hash per image, so the
    # ones we hold are read from the manifest rather than off the disk again.
    # Only soybean can overlap: the other manifests are rice and maize.
    known: list[int] = []
    more = ROOT / "data" / "processed" / "more_images.csv"
    if more.exists():
        for r in csv.DictReader(more.open()):
            if r.get("crop") == "soybean" and r.get("dhash"):
                known.append(int(r["dhash"], 16))
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
                        name = f"{cls}_{Path(m).stem}.jpg"
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
    kept = {}
    for r in rows:
        kept[r["train_class"]] = kept.get(r["train_class"], 0) + 1
    print(f"\nkept {len(rows)} images ({dropped} near-duplicates dropped) -> {MANIFEST}")
    for k, v in sorted(kept.items()):
        print(f"  {v:5d}  {k}")


if __name__ == "__main__":
    main()
