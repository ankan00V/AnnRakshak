"""Maize and cotton photos for classes still short of them, from three Mendeley
Data sets (all CC BY 4.0), each archive checked against its SHA-256.

  3myfctrgk3  MLD: A Multi-Class Maize Leaf Disease Image Dataset from
              Bangladesh (2025). Phone photos, Jhenaidah. Fall armyworm (525),
              gray spot (555), healthy (427).
  5wp23rgtpy  Cotton Aphid Images (MNS University of Agriculture, Multan).
              Cotton leaves under aphid attack; the videos are not used.
  sb4wwjs8bz  An Open-Source Multi-Format Maize Leaf Image Dataset (Bangladesh,
              June 2026). Only the converted raw photos of common rust, gray
              leaf spot and healthy leaves: its augmented copies would only be
              de-duplicated away.

Left out on purpose: "Leaf Blight" / "Corn Leaf Blight" in both maize sets,
because neither says which blight. Ours are two classes — turcicum (northern)
and maydis (southern) — that look different and are managed differently, and a
pile of unsorted blight photos would teach the model to confuse them.
Eyespot, maize streak and bacterial leaf streak are not classes of ours.

Every photo is de-duplicated against everything in data/processed (dHash,
Hamming <= 3) and within this import (<= 4).

    .venv/bin/python data/ingest_mendeley2.py
      -> data/processed/mendeley2_640/<class>/*.jpg, data/processed/mendeley2_images.csv
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "data"))
from composite import is_plain  # noqa: E402
from ingest_more import dhash, near  # noqa: E402

API = "https://data.mendeley.com/public-api/datasets/{id}"
RAW = ROOT / "data" / "raw" / "mendeley2"
OUT = ROOT / "data" / "processed" / "mendeley2_640"
CSV_OUT = ROOT / "data" / "processed" / "mendeley2_images.csv"
EXISTING = [p for p in (ROOT / "data" / "processed").glob("*_640") if p != OUT]
LONG_SIDE = 640
FIELDS = ["path", "train_class", "target", "crop", "source", "bg", "dhash"]
IMG = (".jpg", ".jpeg", ".png")

# (dataset, folder inside it) -> (training class, KB target, crop)
MLD = {
    "Fall_Armyworm": ("maize_fall_armyworm", "maize_fall_armyworm", "maize"),
    "Gray_Spot": ("maize_gray_leaf_spot", "maize_gray_leaf_spot", "maize"),
    "Healthy": ("maize_healthy", "maize_healthy", "maize"),
}
SB4 = {
    "2. Common Rust": ("maize_common_rust", "maize_common_rust", "maize"),
    "3. Gray Leaf Spot": ("maize_gray_leaf_spot", "maize_gray_leaf_spot", "maize"),
    "7. Healthy Leaf": ("maize_healthy", "maize_healthy", "maize"),
}
APHID = ("cotton_aphid", "cotton_aphid", "cotton")


def _curl(url: str, dst: Path) -> None:
    subprocess.run(["curl", "-sfL", "--retry", "3", "--max-time", "1200", "-A", "Mozilla/5.0", "-o", str(dst), url],
                   check=True, timeout=1500)


def _listing(dataset: str) -> dict:
    dst = RAW / f"{dataset}.json"
    if not dst.exists():
        _curl(API.format(id=dataset), dst)
    return json.loads(dst.read_text())


def _verified(f: dict, dst: Path) -> Path | None:
    want = f["content_details"]["sha256_hash"]
    if not (dst.exists() and hashlib.sha256(dst.read_bytes()).hexdigest() == want):
        _curl(f["content_details"]["download_url"], dst)
    return dst if hashlib.sha256(dst.read_bytes()).hexdigest() == want else None


def zip_photos(dataset: str, pick):
    """(class tuple, bytes, source) for each photo in a one-archive dataset."""
    f = _listing(dataset)["files"][0]
    archive = _verified(f, RAW / f"{dataset}.zip")
    if archive is None:
        raise SystemExit(f"{dataset}: archive does not match its SHA-256")
    with zipfile.ZipFile(archive) as z:
        for name in sorted(z.namelist()):
            if name.lower().endswith(IMG) and (cls := pick(name)):
                yield cls, z.read(name), f"mendeley:{dataset}"


def sb4_photos():
    dataset = "sb4wwjs8bz"
    folders = RAW / "sb4_folders.json"
    if not folders.exists():
        _curl(API.format(id=dataset) + "/folders/1", folders)
    fo = {x["id"]: x for x in json.loads(folders.read_text())}

    def path(i):
        parts = []
        while i in fo:
            parts.append(fo[i]["name"])
            i = fo[i].get("parent_id")
        return "/".join(reversed(parts))

    wanted = []
    for f in _listing(dataset)["files"]:
        p = path(f["folder_id"])
        if "/Converted raw Images/" in p and p.rsplit("/", 1)[-1] in SB4 and f["filename"].lower().endswith(IMG):
            wanted.append((f, SB4[p.rsplit("/", 1)[-1]]))
    dst_dir = RAW / dataset
    dst_dir.mkdir(parents=True, exist_ok=True)

    def fetch(item):
        f, cls = item
        try:
            got = _verified(f, dst_dir / f"{cls[0]}__{f['filename']}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None  # one dropped download does not stop the set; a rerun fetches it
        return (cls, got) if got else None

    with ThreadPoolExecutor(8) as pool:
        got = [g for g in pool.map(fetch, wanted) if g]
    print(f"  {dataset}: {len(got)}/{len(wanted)} photos downloaded and checked", flush=True)
    for cls, p in sorted(got, key=lambda g: str(g[1])):
        yield cls, p.read_bytes(), f"mendeley:{dataset}"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    known: set[int] = set()
    for d in EXISTING:
        for p in d.rglob("*.jpg"):
            with Image.open(p) as im:
                known.add(dhash(im))
    known_list = list(known)
    print(f"{len(known)} images already in data/processed", flush=True)

    sources = (
        zip_photos("3myfctrgk3", lambda n: MLD.get(n.split("/")[1]) if n.count("/") >= 2 else None),
        zip_photos("5wp23rgtpy", lambda n: APHID if re.search(r"aphid", n, re.I) else None),
        sb4_photos(),
    )
    rows: list[dict[str, str]] = []
    seen: list[int] = []
    stats: Counter[str] = Counter()
    for source in sources:
        for (cls, target, crop), data, src in source:
            try:
                im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            except Exception:  # noqa: BLE001
                stats["unreadable"] += 1
                continue
            h = dhash(im)
            if h in known or near(h, known_list, 3) or near(h, seen, 4):
                stats[f"duplicate {cls}"] += 1
                continue
            seen.append(h)
            im.thumbnail((LONG_SIDE, LONG_SIDE))
            dst = OUT / cls / f"{len(seen):05d}_{src.split(':')[1]}.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst, "JPEG", quality=88)
            rows.append({"path": str(dst.relative_to(ROOT)), "train_class": cls, "target": target, "crop": crop,
                         "source": src, "bg": "plain" if is_plain(im) else "field", "dhash": f"{h:016x}"})
            stats[f"kept {cls}"] += 1
        print(f"  done a source: {dict(stats)}", flush=True)

    with CSV_OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {CSV_OUT.relative_to(ROOT)}: {len(rows)} new images")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
