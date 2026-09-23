"""Three cotton sets from Mendeley Data, for the gaps cotton still had.

Cotton was carried by two sources and six classes, and two of the things the
app tells farmers to look for had no photograph at all. These fill that in:

  jassid (leaf hopper)   an advisory, weather rules and inspection tasks since
                         September, and until now not one image to learn from
  leaf reddening         not a disease: cotton reddens from cold nights,
                         magnesium or nitrogen shortage and waterlogging, and a
                         farmer who reads it as a disease sprays for nothing
  herbicide damage       also not a disease: drift or an overdose, cupped and
                         strapped leaves. The answer is to stop spraying, which
                         no fungicide advisory would ever say

  b3jy2p6k8w  SAR-CLD-2024 (Islam et al.)          2,144 originals, 8 classes
  t9hgvk2h9p  Cotton Leaf Image Dataset            1,378 originals, 5 classes
  74jsdxtmx2  Cotton Leaf Disease with Severity    1,000 originals, 4 classes

Augmented copies are ignored in all three: every one of these downloads ships
rotations and flips beside the originals, and a flipped copy of a test photo in
the training split is how a model scores well on nothing.

    .venv/bin/python data/ingest_cotton.py
      -> data/processed/cotton_640/<class>/*.jpg
         data/processed/cotton_images.csv
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

RAW = ROOT / "data" / "raw" / "cotton_mendeley"
OUT = ROOT / "data" / "processed" / "cotton_640"
CSV_OUT = ROOT / "data" / "processed" / "cotton_images.csv"
EXISTING = [ROOT / "data" / "processed" / d
            for d in ("icar_640", "extra_640", "more_640", "paddy_640", "asdid_640", "local_640")]
LONG_SIDE = 640
FIELDS = ["path", "train_class", "target", "crop", "source", "bg", "dhash"]

BLIGHT = ("cotton_bacterial_blight", "cotton_bacterial_blight")
CURL = ("cotton_leaf_curl", "cotton_leaf_curl")
HEALTHY = ("cotton_healthy", "cotton_healthy")
# Fusarium and Verticillium wilt are one target on purpose: they cannot be told
# apart from a leaf photo and the field response is the same (see DATASETS.md).
WILT = ("cotton_wilt", "cotton_wilt")
ALTERNARIA = ("cotton_alternaria_leaf_spot", "cotton_alternaria_leaf_spot")
JASSID = ("cotton_jassid", "cotton_jassid")
REDDENING = ("cotton_leaf_reddening", "cotton_leaf_reddening")
HERBICIDE = ("cotton_herbicide_damage", "cotton_herbicide_damage")

# zip -> {path fragment (lower-case) somewhere in the member name: class}
SOURCES: dict[str, dict[str, tuple[str, str]]] = {
    "b3jy2p6k8w": {
        "bacterial blight": BLIGHT, "curl virus": CURL, "healthy leaf": HEALTHY,
        "leaf hopper jassids": JASSID, "leaf redding": REDDENING,
        "herbicide growth damage": HERBICIDE,
        # "leaf variegation" is left out: variegation has several causes, viral
        # and genetic, and the app would have nothing certain to say about it.
    },
    "t9hgvk2h9p": {
        "bacterial blight": BLIGHT, "healthy leaf": HEALTHY,
        "fusarium wilt": WILT, "verticillium wilt": WILT, "alternaria leaf spot": ALTERNARIA,
    },
    "74jsdxtmx2": {  # severity folders (mild/moderate/critical) all map to the problem itself
        "bacterial blight": BLIGHT, "curl virus": CURL, "fussarium wilt": WILT, "healthy": HEALTHY,
    },
}


def main() -> None:
    known: set[int] = set()
    for d in EXISTING:
        for p in d.rglob("*.jpg"):
            with Image.open(p) as im:
                known.add(dhash(im))
    known_list = list(known)
    print(f"{len(known)} images already in data/processed", flush=True)

    rows: list[dict[str, str]] = []
    seen: dict[str, list[int]] = {}
    for source, folders in SOURCES.items():
        zip_path = RAW / f"{source}.zip"
        if not zip_path.exists():
            raise SystemExit(f"missing {zip_path.relative_to(ROOT)}")
        stats: Counter[str] = Counter()
        with zipfile.ZipFile(zip_path) as zf:
            for name in sorted(zf.namelist()):
                if not name.lower().endswith((".jpg", ".jpeg", ".png")) or "__MACOSX" in name:
                    continue
                low = name.lower()
                match = next(((frag, cls) for frag, cls in folders.items() if frag in low), None)
                if match is None:
                    stats["not a class we keep"] += 1
                    continue
                cls, target = match[1]
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
                dst = OUT / cls / f"{source}_{len(pool):05d}_{Path(name).stem[:30]}.jpg"
                dst.parent.mkdir(parents=True, exist_ok=True)
                im.save(dst, "JPEG", quality=88)
                rows.append({"path": str(dst.relative_to(ROOT)), "train_class": cls, "target": target,
                             "crop": "cotton", "source": source, "bg": "plain" if is_plain(im) else "field",
                             "dhash": f"{h:016x}"})
                stats["kept"] += 1
        print(f"  {source}: {dict(stats)}", flush=True)
        with CSV_OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)

    print(f"\nwrote {CSV_OUT.relative_to(ROOT)}: {len(rows)} images")
    kept = Counter(r["train_class"] for r in rows)
    field = Counter(r["train_class"] for r in rows if r["bg"] == "field")
    for cls in sorted(kept):
        print(f"  {cls:32s} {kept[cls]:5d}  ({field[cls]} field)")


if __name__ == "__main__":
    main()
