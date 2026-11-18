"""Northern leaf blight (turcicum) photographed in the field, from the CD&S
dataset (Ahmad, Saraswat, El Gamal and Johal, Purdue University; arXiv
2110.12084; OSF project s6ru5).

Handheld photos from maize field trials, sorted by disease by the researchers
who took them. Only "Dataset_Original", the raw photos, is used: the set's
other folders are the same photos with the background cut out or replaced,
and those would land in both our training and our test split. Its gray leaf
spot is not taken (we have plenty), and northern leaf spot is not a problem
the app advises on.

Why: turcicum had 67 held-out photos and was the maize class the gate trusted
least (0.945 precision at its highest bar). Its field photos came mostly from
PlantVillage-style close-ups. A set of real turcicum photos was looked for
elsewhere and not found usable: the Cornell NLB set's lesion annotations are
gone from OSF, and about 4 in 10 of its photos have no visible lesion, so
without them the label would be wrong that often; the "Leaf Blight" folders in
the Bangladesh sets do not say which blight (data/DATASETS.md §12).

Each file is downloaded on its own and checked against the SHA-256 OSF
publishes for it, then de-duplicated against everything in data/processed
(dHash, Hamming <= 3) and within this import (<= 4).

    .venv/bin/python data/ingest_cds.py
      -> data/processed/cds_640/maize_turcicum_leaf_blight/*.jpg, data/processed/cds_images.csv
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "data"))
from composite import is_plain  # noqa: E402
from ingest_more import dhash, near  # noqa: E402

API = "https://api.osf.io/v2/nodes/s6ru5/files/osfstorage/"
RAW = ROOT / "data" / "raw" / "cds"
OUT = ROOT / "data" / "processed" / "cds_640"
CSV_OUT = ROOT / "data" / "processed" / "cds_images.csv"
EXISTING = [p for p in (ROOT / "data" / "processed").glob("*_640") if p != OUT]
FIELDS = ["path", "train_class", "target", "crop", "source", "bg", "dhash"]
CLS = "maize_turcicum_leaf_blight"


def _get(url: str, binary: bool = False):
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                        timeout=120) as r:
                data = r.read()
            return data if binary else json.loads(data)
        except Exception:  # noqa: BLE001  OSF drops and rate-limits now and then: back off and retry
            time.sleep(4 + 4 * attempt)
    raise OSError(f"could not fetch {url[:100]}")


def _children(url: str) -> list[dict]:
    out = []
    while url:
        d = _get(url)
        out += d["data"]
        url = d["links"].get("next")
    return out


def _sub(node: dict) -> str:
    return node["relationships"]["files"]["links"]["related"]["href"]


def nlb_files() -> list[dict]:
    root = _children(API)[0]  # "CD&S"
    original = next(x for x in _children(_sub(root)) if x["attributes"]["name"] == "Dataset_Original")
    files = []
    for split in _children(_sub(original)):
        nlb = next(x for x in _children(_sub(split)) if x["attributes"]["name"] == "nlb")
        files += [f for f in _children(_sub(nlb)) if f["attributes"]["kind"] == "file"]
    return files


def fetch(f: dict) -> Path | None:
    a = f["attributes"]
    dst = RAW / a["name"]
    want = (a.get("extra") or {}).get("hashes", {}).get("sha256")
    if not (dst.exists() and want and hashlib.sha256(dst.read_bytes()).hexdigest() == want):
        try:
            dst.write_bytes(_get(f["links"]["download"], binary=True))
        except OSError:
            return None  # a dropped download; a rerun fetches it
    if want and hashlib.sha256(dst.read_bytes()).hexdigest() != want:
        dst.unlink()
        return None
    return dst


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    known = []
    for d in EXISTING:
        for p in d.rglob("*.jpg"):
            with Image.open(p) as im:
                known.append(dhash(im))
    files = nlb_files()
    with ThreadPoolExecutor(6) as pool:
        got = [p for p in pool.map(fetch, files) if p]
    print(f"{len(got)}/{len(files)} photos downloaded and checked", flush=True)
    rows, seen, stats = [], [], Counter()
    for p in sorted(got):
        try:
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(p.read_bytes()))).convert("RGB")
        except Exception:  # noqa: BLE001
            stats["unreadable"] += 1
            continue
        h = dhash(im)
        if near(h, known, 3) or near(h, seen, 4):
            stats["duplicate"] += 1
            continue
        seen.append(h)
        im.thumbnail((640, 640))
        dst = OUT / CLS / f"{p.stem}.jpg"
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, "JPEG", quality=88)
        rows.append({"path": str(dst.relative_to(ROOT)), "train_class": CLS, "target": CLS, "crop": "maize",
                     "source": "osf:s6ru5", "bg": "plain" if is_plain(im) else "field", "dhash": f"{h:016x}"})
        stats["kept"] += 1
    with CSV_OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {CSV_OUT.relative_to(ROOT)}: {len(rows)} photos {dict(stats)}")


if __name__ == "__main__":
    main()
