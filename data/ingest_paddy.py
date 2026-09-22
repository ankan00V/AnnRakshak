"""Paddy Doctor: 10,407 labelled rice photos from Tamil Nadu fields.

What our rice classes were missing was field photos. Rice healthy had 1,530
images and not one taken in a field — all single leaves on white paper — so
background randomisation (ml/composite.py) had only 34 rice field photos to
paste onto, and held-out rice recall fell to 0.59 with the backdrop swapped.
These are whole plants shot on a phone in the field, with the variety and the
crop's age recorded.

All ten classes map onto targets the app advises on: the four that had no
advisory (hispa, downy mildew, bacterial leaf streak, bacterial panicle
blight) were written into backend/kb on 2026-09-23, because the model must
never name something the app cannot then explain.

Dead heart is the damage a stem borer leaves. The dataset does not say which
borer; in Tamil Nadu paddy it is nearly always the yellow stem borer, so it is
filed there (ml/reports says so too).

    KAGGLE_API_TOKEN=... .venv/bin/kaggle datasets download -d imbikramsaha/paddy-doctor -p data/raw/paddy_doctor
    .venv/bin/python data/ingest_paddy.py
      -> data/processed/paddy_640/<class>/*.jpg
         data/processed/paddy_images.csv  (path, train_class, target, crop, source, bg, dhash, variety, age)
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "data"))
from composite import is_plain  # noqa: E402
from ingest_more import dhash, near  # noqa: E402

ZIP = ROOT / "data" / "raw" / "paddy_doctor" / "paddy-doctor.zip"
INNER = "paddy-disease-classification"
OUT = ROOT / "data" / "processed" / "paddy_640"
CSV_OUT = ROOT / "data" / "processed" / "paddy_images.csv"
EXISTING = [ROOT / "data" / "processed" / d for d in ("icar_640", "extra_640", "more_640")]
LONG_SIDE = 640
SOURCE = "paddy_doctor"

# Paddy Doctor label -> (our training class, our KB target)
USE = {
    "normal": ("rice_healthy", "rice_healthy"),
    "blast": ("rice_leaf_blast", "rice_blast"),
    "brown_spot": ("rice_brown_spot", "rice_brown_spot"),
    "bacterial_leaf_blight": ("rice_bacterial_leaf_blight", "rice_bacterial_leaf_blight"),
    "tungro": ("rice_tungro", "rice_tungro"),
    "dead_heart": ("rice_yellow_stem_borer", "rice_yellow_stem_borer"),
    # advisories written 2026-09-23 (backend/kb): the app can now name these too
    "hispa": ("rice_hispa", "rice_hispa"),
    "downy_mildew": ("rice_downy_mildew", "rice_downy_mildew"),
    "bacterial_leaf_streak": ("rice_bacterial_leaf_streak", "rice_bacterial_leaf_streak"),
    "bacterial_panicle_blight": ("rice_bacterial_panicle_blight", "rice_bacterial_panicle_blight"),
}
SKIP: tuple[str, ...] = ()  # every Paddy Doctor class now has an advisory


def main() -> None:
    if not ZIP.exists():
        raise SystemExit(f"no {ZIP.relative_to(ROOT)} — download it first (see the docstring)")
    known: dict[int, str] = {}
    for d in EXISTING:
        for p in d.rglob("*.jpg"):
            with Image.open(p) as im:
                known[dhash(im)] = str(p.relative_to(ROOT))
    print(f"{len(known)} images already in data/processed")
    known_list = list(known)

    with zipfile.ZipFile(ZIP) as zf:
        labels = {r["image_id"]: r for r in csv.DictReader(io.TextIOWrapper(zf.open(f"{INNER}/train.csv")))}
        rows, stats = [], defaultdict(Counter)
        seen_in_class: dict[str, list[int]] = defaultdict(list)
        names = sorted(n for n in zf.namelist() if n.startswith(f"{INNER}/train_images/") and n.lower().endswith(".jpg"))
        for i, name in enumerate(names, 1):
            label = Path(name).parent.name
            if label in SKIP or label not in USE:
                stats[label]["no advisory: skipped"] += 1
                continue
            cls, target = USE[label]
            try:
                im = ImageOps.exif_transpose(Image.open(io.BytesIO(zf.read(name)))).convert("RGB")
            except Exception:  # noqa: BLE001  unreadable file
                stats[label]["unreadable"] += 1
                continue
            h = dhash(im)
            if h in known or near(h, known_list, 3):
                stats[label]["duplicate of existing"] += 1
                continue
            if near(h, seen_in_class[cls]):
                stats[label]["duplicate within new"] += 1
                continue
            seen_in_class[cls].append(h)
            im.thumbnail((LONG_SIDE, LONG_SIDE))
            dst = OUT / cls / f"{len(seen_in_class[cls]):05d}_{Path(name).stem[:40]}.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst, "JPEG", quality=88)
            meta = labels.get(Path(name).name, {})
            rows.append({"path": str(dst.relative_to(ROOT)), "train_class": cls, "target": target, "crop": "rice",
                         "source": SOURCE, "bg": "plain" if is_plain(im) else "field", "dhash": f"{h:016x}",
                         "variety": meta.get("variety", ""), "age": meta.get("age", "")})
            stats[label]["kept"] += 1
            if i % 1000 == 0:
                print(f"  {i}/{len(names)} read", flush=True)

    with CSV_OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {CSV_OUT.relative_to(ROOT)}: {len(rows)} images")
    for label, c in sorted(stats.items()):
        print(f"  {label:26s} {dict(c)}")
    kept = Counter(r["train_class"] for r in rows)
    field = Counter(r["train_class"] for r in rows if r["bg"] == "field")
    for cls in sorted(kept):
        print(f"  {cls:28s} {kept[cls]:5d}  ({field[cls]} field)")


if __name__ == "__main__":
    main()
