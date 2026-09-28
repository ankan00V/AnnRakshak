"""Five image sets the team downloaded by hand, mostly rice from Bangladesh.

Paddy Doctor gave rice 8,920 field photos, all from Tamil Nadu, one season,
one phone. These add other countries, other cameras and other seasons for the
four rice problems a farmer sends most often, and a second source for soybean
caterpillar damage, which until now came entirely from one Maharashtra set.

    .venv/bin/python data/ingest_downloads.py
      -> data/processed/local_640/<class>/*.jpg
         data/processed/local_images.csv  (path, train_class, target, crop, source, bg, dhash)

Read from ~/Downloads and copied, never moved: the originals stay where the
team put them.

Left out on purpose, and why:
  Diabrotica speciosa (2,205 photos)  a South American beetle. It is not in
      India, so naming it would be naming something a farmer's field cannot
      have.
  Maize streak virus (401)            African, same reason.
  "Maize leaf blight" (493)           does not say turcicum or maydis, and the
      app treats those as separate problems with different advisories.
  The folder called "Rice" (585)      rice panicles on white paper with no
      problem named. A label cannot be invented.
  Augmented copies (8,258)            rotations and flips of the originals in
      the same download; training makes its own, and a rotated copy of a test
      photo sitting in the training split is how a model scores well on
      nothing.
  mask-vesrion1 (5,932)               segmentation masks for "Rice Leaf Disease
      Images", not photographs.
  The rice-panicle COCO sets          detection boxes, no disease label.
  Potato, tomato, cashew              not crops this app advises on.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "data"))
from composite import is_plain  # noqa: E402
from ingest_more import dhash, near  # noqa: E402

DOWNLOADS = Path.home() / "Downloads"
OUT = ROOT / "data" / "processed" / "local_640"
CSV_OUT = ROOT / "data" / "processed" / "local_images.csv"
EXISTING = [ROOT / "data" / "processed" / d
            for d in ("icar_640", "extra_640", "more_640", "paddy_640", "asdid_640")]
LONG_SIDE = 640
FIELDS = ["path", "train_class", "target", "crop", "source", "bg", "dhash"]

RICE = {
    "blast": ("rice_leaf_blast", "rice_blast"),
    "blb": ("rice_bacterial_leaf_blight", "rice_bacterial_leaf_blight"),
    "brown": ("rice_brown_spot", "rice_brown_spot"),
    "tungro": ("rice_tungro", "rice_tungro"),
    "healthy": ("rice_healthy", "rice_healthy"),
}

# source id -> (folder under ~/Downloads, {subfolder: key into RICE or an explicit pair}, crop)
SOURCES: dict[str, tuple[str, dict[str, object], str]] = {
    # RiceLeafBD: real-field phone photos from Bangladesh (Mendeley).
    "riceleafbd": ("Original Images", {
        "Bacterial Leaf Blight": "blb", "Brown Spot": "brown",
        "Healthy Leaf": "healthy", "Tungro Virus": "tungro",
    }, "rice"),
    # Rice Leaf and Crop Disease Detection Dataset — originals only ("orginal"
    # is the folder's own spelling); its augmented copies are skipped.
    "rice_bd_field": ("Rice Leaf and Crop Disease Detection Dataset-Rice Leaf and Crop Disease Detection Dataset", {
        "Bacterial Leaf Blight/orginal": "blb", "Healthy _leaf/orginal": "healthy",
        "Rice Blast/orginal": "blast", "Tungro/orginal": "tungro",
    }, "rice"),
    # The 5,932-image rice leaf set (the one mask-vesrion1 carries masks for).
    "rice_leaf_5932": ("Rice Leaf Disease Images", {
        "Bacterialblight": "blb", "Blast": "blast", "Brownspot": "brown", "Tungro": "tungro",
    }, "rice"),
    # A mixed multi-crop download; only its rice and its healthy maize are ours.
    "crops_multi": ("Crops", {
        "Rice/bacterial_leaf_blight": "blb", "Rice/brown_spot": "brown",
        "Rice/leaf_blast": "blast", "Rice/rice_healthy": "healthy",
        "Corn/Maize healthy": ("maize_healthy", "maize_healthy", "maize"),
    }, "rice"),
    # Brazilian soybean canopy photos. The caterpillar there is not the same
    # species as ours, but what the model learns is chewed leaves, and the
    # advisory behind our target (tobacco caterpillar) is the one an Indian
    # farmer needs when a defoliator is eating the crop.
    "soy_brazil": ("bycbh73438-1", {
        "Caterpillar": ("soybean_caterpillar_damage", "soybean_tobacco_caterpillar", "soybean"),
        "Healthy": ("soybean_healthy", "soybean_healthy", "soybean"),
    }, "soybean"),
}


def known_hashes() -> tuple[set[int], list[int]]:
    known: set[int] = set()
    for d in EXISTING:
        for p in d.rglob("*.jpg"):
            with Image.open(p) as im:
                known.add(dhash(im))
    return known, list(known)


def main() -> None:
    missing = [s for s, (folder, _, _) in SOURCES.items() if not (DOWNLOADS / folder).is_dir()]
    if missing:
        raise SystemExit(f"not in ~/Downloads: {', '.join(missing)}")
    known, known_list = known_hashes()
    print(f"{len(known)} images already in data/processed", flush=True)

    rows: list[dict[str, str]] = []
    seen: dict[str, list[int]] = {}
    for source, (folder, folders, default_crop) in SOURCES.items():
        for sub, how in folders.items():
            stats: Counter[str] = Counter()  # per folder: the interesting number is how much of each set is new
            if isinstance(how, str):
                cls, target = RICE[how]
                crop = default_crop
            else:
                cls, target, crop = how
            files = sorted(p for p in (DOWNLOADS / folder / sub).rglob("*")
                           if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
            for p in files:
                try:
                    im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
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
                dst = OUT / cls / f"{source}_{len(pool):05d}_{p.stem[:34]}.jpg"
                dst.parent.mkdir(parents=True, exist_ok=True)
                im.save(dst, "JPEG", quality=88)
                rows.append({"path": str(dst.relative_to(ROOT)), "train_class": cls, "target": target,
                             "crop": crop, "source": source, "bg": "plain" if is_plain(im) else "field",
                             "dhash": f"{h:016x}"})
                stats["kept"] += 1
            print(f"  {source}/{sub} -> {cls}: {dict(stats)}", flush=True)
        with CSV_OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)

    print(f"\nwrote {CSV_OUT.relative_to(ROOT)}: {len(rows)} images")
    kept = Counter(r["train_class"] for r in rows)
    field = Counter(r["train_class"] for r in rows if r["bg"] == "field")
    for cls in sorted(kept):
        print(f"  {cls:30s} {kept[cls]:5d}  ({field[cls]} field)")
    by_source = Counter(r["source"] for r in rows)
    print("  " + "  ".join(f"{s}={n}" for s, n in by_source.items()))


if __name__ == "__main__":
    main()
