"""The second wave of image sources (September 2026): soybean and cotton for the
first time, more rice and maize. Reads the downloads, maps folders to our
training classes, drops near-duplicates (within the new data AND against every
image already in data/processed/, so nothing can sit in both a training and a
test split), resizes to 640 px and records provenance.

    .venv/bin/python data/ingest_more.py
      -> data/processed/more_640/<source>/<class>/*.jpg
         data/processed/more_images.csv  (path, train_class, target, crop, source, bg, dhash)

Skipped on purpose: wheat and sugarcane (not our crops), UAV images (not what a
farmer's phone sees), Cotton_Augmented_Dataset (synthetic copies of the
originals would inflate every metric), and folders with too few unique images
to learn from (see MIN_IMAGES).
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
from composite import is_plain  # noqa: E402

DL = Path.home() / "Downloads"
OUT = ROOT / "data" / "processed" / "more_640"
CSV = ROOT / "data" / "processed" / "more_images.csv"
EXISTING = [ROOT / "data" / "processed" / "icar_640", ROOT / "data" / "processed" / "extra_640"]
MIN_IMAGES = 100   # a class needs this many unique images to be learnt at all
LONG_SIDE = 640
SOY = "MH-SoyaHealthVision An Indian UAV and Leaf Image Dataset for Integrated Crop Health Assessment/Soyabean_Leaf_Image_Dataset"

# (source id, folder or zip under ~/Downloads, our train_class, KB target)
SOURCES = [
    # --- soybean: MH-SoyaHealthVision leaf images (Maharashtra fields, phone photos)
    ("mh_soya", f"{SOY}/Soyabean_Rust.zip", "soybean_rust", "soybean_rust"),
    ("mh_soya", f"{SOY}/Soyabean_Mosaic.zip", "soybean_yellow_mosaic", "soybean_yellow_mosaic"),
    ("mh_soya", f"{SOY}/Caterpillar and Semilooper Pest Attack.zip", "soybean_caterpillar_damage", "soybean_tobacco_caterpillar"),
    ("mh_soya", f"{SOY}/Soyabean_Frog_Leaf_Eye.zip", "soybean_frogeye_leaf_spot", "soybean_frogeye_leaf_spot"),
    ("mh_soya", f"{SOY}/Soyabean_Spectoria_Brown_Spot.zip", "soybean_septoria_brown_spot", "soybean_septoria_brown_spot"),
    ("mh_soya", f"{SOY}/Healthy_Soyabean.zip", "soybean_healthy", "soybean_healthy"),
    # --- soybean: a second, smaller set (segmented leaves)
    ("soy_leaves", "archive-2/ferrugen", "soybean_rust", "soybean_rust"),
    ("soy_leaves", "archive-2/Yellow Mosaic", "soybean_yellow_mosaic", "soybean_yellow_mosaic"),
    ("soy_leaves", "archive-2/brown_spot", "soybean_septoria_brown_spot", "soybean_septoria_brown_spot"),
    ("soy_leaves", "archive-2/septoria", "soybean_septoria_brown_spot", "soybean_septoria_brown_spot"),
    # --- cotton
    ("cotton_orig", "Cotton_Original_Dataset/Bacterial Blight", "cotton_bacterial_blight", "cotton_bacterial_blight"),
    ("cotton_orig", "Cotton_Original_Dataset/Alternaria Leaf Spot", "cotton_alternaria_leaf_spot", "cotton_alternaria_leaf_spot"),
    ("cotton_orig", "Cotton_Original_Dataset/Fusarium Wilt", "cotton_wilt", "cotton_wilt"),
    ("cotton_orig", "Cotton_Original_Dataset/Verticillium Wilt", "cotton_wilt", "cotton_wilt"),
    ("cotton_orig", "Cotton_Original_Dataset/Healthy Leaf", "cotton_healthy", "cotton_healthy"),
    ("crops_mix", "archive/Train/bacterial_blight in Cotton", "cotton_bacterial_blight", "cotton_bacterial_blight"),
    ("crops_mix", "archive/Validation/Bacterial Blight in cotton", "cotton_bacterial_blight", "cotton_bacterial_blight"),
    ("crops_mix", "archive/Train/Leaf Curl", "cotton_leaf_curl", "cotton_leaf_curl"),
    ("crops_mix", "archive/Validation/Leaf Curl", "cotton_leaf_curl", "cotton_leaf_curl"),
    ("crops_mix", "archive/Train/Wilt", "cotton_wilt", "cotton_wilt"),
    ("crops_mix", "archive/Validation/Wilt", "cotton_wilt", "cotton_wilt"),
    ("crops_mix", "archive/Train/Healthy cotton", "cotton_healthy", "cotton_healthy"),
    ("crops_mix", "archive/Validation/Healthy cotton", "cotton_healthy", "cotton_healthy"),
    ("crops_mix", "archive/Train/Cotton Aphid", "cotton_aphid", "cotton_aphid"),
    ("crops_mix", "archive/Validation/Cotton Aphid", "cotton_aphid", "cotton_aphid"),
    ("crops_mix", "archive/Train/cotton mealy bug", "cotton_mealybug", "cotton_mealybug"),
    ("crops_mix", "archive/Validation/cotton mealy bug", "cotton_mealybug", "cotton_mealybug"),
    ("crops_mix", "archive/Train/cotton whitefly", "cotton_whitefly", "cotton_whitefly"),
    ("crops_mix", "archive/Validation/cotton whitefly", "cotton_whitefly", "cotton_whitefly"),
    ("crops_mix", "archive/Train/American Bollworm on Cotton", "cotton_american_bollworm", "cotton_american_bollworm"),
    ("crops_mix", "archive/Validation/American Bollworm on Cotton", "cotton_american_bollworm", "cotton_american_bollworm"),
    ("crops_mix", "archive/Train/pink bollworm in cotton", "cotton_pink_bollworm", "cotton_pink_bollworm"),
    ("crops_mix", "archive/Validation/pink bollworm in cotton", "cotton_pink_bollworm", "cotton_pink_bollworm"),
    # --- maize
    ("crops_mix", "archive/Train/Common_Rust", "maize_common_rust", "maize_common_rust"),
    ("crops_mix", "archive/Train/Gray_Leaf_Spot", "maize_gray_leaf_spot", "maize_gray_leaf_spot"),
    ("crops_mix", "archive/Validation/Gray_Leaf_Spot", "maize_gray_leaf_spot", "maize_gray_leaf_spot"),
    ("crops_mix", "archive/Train/Healthy Maize", "maize_healthy", "maize_healthy"),
    ("crops_mix", "archive/Train/maize ear rot", "maize_ear_rot", "maize_ear_rot"),
    ("crops_mix", "archive/Validation/maize ear rot", "maize_ear_rot", "maize_ear_rot"),
    ("crops_mix", "archive/Train/maize fall armyworm", "maize_fall_armyworm", "maize_fall_armyworm"),
    ("crops_mix", "archive/Validation/maize fall armyworm", "maize_fall_armyworm", "maize_fall_armyworm"),
    ("crops_mix", "archive/Train/maize stem borer", "maize_stem_borer", "maize_stem_borer"),
    ("crops_mix", "archive/Validation/maize stem borer", "maize_stem_borer", "maize_stem_borer"),
    ("idadp", "IDADP-Corn-Descriptions_600/image/大斑病", "maize_turcicum_leaf_blight", "maize_turcicum_leaf_blight"),
    ("idadp", "IDADP-Corn-Descriptions_600/image/小斑病", "maize_maydis_leaf_blight", "maize_maydis_leaf_blight"),
    ("idadp", "IDADP-Corn-Descriptions_600/image/锈病", "maize_common_rust", "maize_common_rust"),
    ("idadp", "IDADP-Corn-Descriptions_600/image/穗腐病", "maize_ear_rot", "maize_ear_rot"),
    ("idadp", "IDADP-Corn-Descriptions_600/image/健康", "maize_healthy", "maize_healthy"),
    # --- rice
    ("crops_mix", "archive/Train/Rice Blast", "rice_leaf_blast", "rice_blast"),
    ("crops_mix", "archive/Validation/Rice Blast", "rice_leaf_blast", "rice_blast"),
    ("crops_mix", "archive/Train/Becterial Blight in Rice", "rice_bacterial_leaf_blight", "rice_bacterial_leaf_blight"),
    ("crops_mix", "archive/Train/Brownspot", "rice_brown_spot", "rice_brown_spot"),
    ("crops_mix", "archive/Train/Tungro", "rice_tungro", "rice_tungro"),
    ("crops_mix", "archive/Validation/Tungro", "rice_tungro", "rice_tungro"),
    ("plantvillage_mix", "train/Rice___Brown_Spot", "rice_brown_spot", "rice_brown_spot"),
    ("icar_copy", "Rice_and_Maize_Dataset", None, None),  # checked for duplicates only
]
IMG = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".jfif")


def dhash(im: Image.Image) -> int:
    g = np.asarray(im.convert("L").resize((9, 8), Image.BILINEAR), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def iter_images(path: Path):
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            for n in sorted(zf.namelist()):
                if n.lower().endswith(IMG):
                    yield Path(n).name, zf.read(n)
    else:
        for p in sorted(path.rglob("*")):
            if p.suffix.lower() in IMG:
                yield p.name, p.read_bytes()


def near(h: int, seen: list[int], tol: int = 4) -> bool:
    return any(bin(h ^ s).count("1") <= tol for s in seen)


def main() -> None:
    known: dict[int, str] = {}
    for d in EXISTING:
        for p in d.rglob("*.jpg"):
            with Image.open(p) as im:
                known[dhash(im)] = str(p.relative_to(ROOT))
    print(f"{len(known)} images already in data/processed")
    known_list = list(known)
    rows, stats = [], defaultdict(Counter)
    per_class_hashes: dict[str, list[int]] = defaultdict(list)
    for source, rel, cls, target in SOURCES:
        path = DL / rel
        if not path.exists():
            print(f"  missing, skipped: {rel}")
            continue
        for name, data in iter_images(path):
            try:
                im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            except Exception:  # noqa: BLE001  unreadable file
                stats[rel]["unreadable"] += 1
                continue
            h = dhash(im)
            if h in known or near(h, known_list, 3):
                stats[rel]["duplicate of existing"] += 1
                continue
            if cls is None:
                stats[rel]["new (not used)"] += 1
                continue
            if near(h, per_class_hashes[cls]):
                stats[rel]["duplicate within new"] += 1
                continue
            per_class_hashes[cls].append(h)
            im.thumbnail((LONG_SIDE, LONG_SIDE))
            dst = OUT / source / cls / f"{len(per_class_hashes[cls]):05d}_{Path(name).stem[:40]}.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst, "JPEG", quality=88)
            rows.append({"path": str(dst.relative_to(ROOT)), "train_class": cls, "target": target,
                         "crop": cls.split("_")[0], "source": source, "bg": "plain" if is_plain(im) else "field",
                         "dhash": f"{h:016x}"})
            stats[rel]["kept"] += 1
        print(f"  {rel[-60:]:60s} {dict(stats[rel])}", flush=True)

    counts = Counter(r["train_class"] for r in rows)
    small = {c for c, n in counts.items() if n < MIN_IMAGES}
    rows = [r for r in rows if r["train_class"] not in small]
    with CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {CSV.relative_to(ROOT)}: {len(rows)} images")
    for c, n in sorted(counts.items()):
        flag = "  (too few — not used)" if c in small else ""
        bg = Counter(r["bg"] for r in rows if r["train_class"] == c)
        print(f"  {c:34s} {n:5d}  {dict(bg)}{flag}")


if __name__ == "__main__":
    main()
