"""False smut photos: the Sambalpur University set on Mendeley Data, and the
one clean class of the Vietnamese rice set on Hugging Face.

  Mendeley Data gpsft4c2zy, "RICE FALSE SMUT" (Sethy et al., Sambalpur
      University, Odisha; CC BY 4.0). 44 field photos, orange and late black
      stages. One archive, checked against its SHA-256.
  minhhungg/rice-disease-dataset (Apache-2.0). Its "False Smut" class: 50 field
      photos of infected panicles. Read straight from the Parquet shard a row
      group at a time (data/hf_range.py).

Why: false smut had 50 photos, all close-ups from one set, and a farmer's wider
shot of an infected panicle was named bacterial leaf blight.

The rest of the Vietnamese set was imported, looked at, and turned down
(17 Nov 2026). Most of its photos are generated copies, not photographs: 925 of
1,560 sheath blight, 204 of 209 bacterial leaf blight and 319 of 394 tungro
have the smeared border of a shifted image, and many pest photos are mirrored
copies of each other (mirrored text gives them away). Copies teach nothing new
and leak one photo into both the training and the test split, which flatters
the score. What was left was web-scraped — collages, QR codes, stock-photo
watermarks — and its leaf folder and yellow stem borer are portraits of the
adult moth, where ours are the damage a farmer photographs. Its false smut is
the exception: real panicles, one smeared copy, five mirrored.

Both checks run on every Vietnamese photo kept: a smeared border (a strip
along an edge whose rows barely change) and a mirrored or rotated copy of a
photo already kept. They are not run on the Sambalpur set: they misread soft
out-of-focus backgrounds and burst shots of one panicle as copies, and that set
was curated by the researchers who took it. Every photo is also de-duplicated against everything in
data/processed (dHash, Hamming <= 3) and within this import (<= 4).

    .venv/bin/python data/ingest_vnrice.py        (HF_TOKEN read from .env)
      -> data/processed/vnrice_640/<class>/*.jpg, data/processed/vnrice_images.csv
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import random
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "data"))
from composite import is_plain  # noqa: E402
from ingest_more import dhash, near  # noqa: E402

try:
    from dotenv import load_dotenv  # noqa: PLC0415

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import pyarrow.parquet as pq  # noqa: E402

from hf_range import RangeFile  # noqa: E402

REPO = "minhhungg/rice-disease-dataset"
SHARDS = ("diseases-", "pests-", "healthy-")
MENDELEY = "https://data.mendeley.com/public-api/datasets/gpsft4c2zy"
RAW = ROOT / "data" / "raw" / "vnrice"
RAW_FS = ROOT / "data" / "raw" / "falsesmut"
OUT = ROOT / "data" / "processed" / "vnrice_640"
CSV_OUT = ROOT / "data" / "processed" / "vnrice_images.csv"
EXISTING = [p for p in (ROOT / "data" / "processed").glob("*_640") if p != OUT]
LONG_SIDE = 640
FIELDS = ["path", "train_class", "target", "crop", "source", "bg", "dhash"]

# label -> (training class, KB target, cap: None = every photo)
MAP = {
    "False Smut": ("rice_false_smut", "rice_false_smut", None),
}


def _shards() -> dict[str, int]:
    req = urllib.request.Request(f"https://huggingface.co/api/datasets/{REPO}/tree/main/data",
                                 headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"})
    for attempt in range(10):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return {x["path"]: x["size"] for x in json.load(r) if any(s in x["path"] for s in SHARDS)}
        except OSError:  # includes a failed certificate check: retried, never accepted
            time.sleep(min(30, 2 * (attempt + 1)))
    raise SystemExit("could not list the dataset's files")


def _read(f, g: int, column: str) -> list:
    """One column of one row group, retried: the Hub drops a range read now and then."""
    for attempt in range(4):
        try:
            return f.read_row_group(g, columns=[column]).column(column).to_pylist()
        except OSError:
            if attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))
    return []


def hf_photos(done: set[str], taken: Counter[str], mark):
    """(label, image bytes) for the mapped labels, capped, in a fixed order.
    Row groups listed in `done` were finished on an earlier run and are skipped;
    `mark` records each one as it finishes."""
    rng = random.Random(7)
    for path, size in sorted(_shards().items()):
        f = pq.ParquetFile(RangeFile(REPO, path, size))
        for g in range(f.metadata.num_row_groups):
            key = f"{path}#{g}"
            if key in done:
                continue
            labels = _read(f, g, "label")
            keep = []
            for i, lab in enumerate(labels):
                if lab not in MAP:
                    continue
                cap = MAP[lab][2]
                # a capped class keeps about the share it needs from each group
                if cap is not None and (taken[lab] >= cap or rng.random() > 0.35):
                    continue
                taken[lab] += 1
                keep.append(i)
            if keep:
                images = _read(f, g, "image")
                for i in keep:
                    yield labels[i], images[i]["bytes"], f"hf:{REPO}"
            print(f"  {path} group {g}: {len(keep)} kept", flush=True)
            mark(key)


def mendeley_photos():
    RAW_FS.mkdir(parents=True, exist_ok=True)
    listing = RAW_FS / "listing.json"
    if not listing.exists():
        subprocess.run(["curl", "-sfL", "--max-time", "120", "-o", str(listing), MENDELEY], check=True)
    f = json.loads(listing.read_text())["files"][0]
    archive = RAW_FS / f["filename"]
    want = f["content_details"]["sha256_hash"]
    if not (archive.exists() and hashlib.sha256(archive.read_bytes()).hexdigest() == want):
        subprocess.run(["curl", "-sfL", "--retry", "3", "--max-time", "300", "-o", str(archive),
                        f["content_details"]["download_url"]], check=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != want:
        raise SystemExit("false smut archive does not match its SHA-256")
    out = RAW_FS / "x"
    if not out.exists():
        out.mkdir()
        subprocess.run(["tar", "-xf", str(archive), "-C", str(out)], check=True)
    for p in sorted(out.rglob("*")):
        if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
            yield "False Smut", p.read_bytes(), "mendeley:gpsft4c2zy"


def smeared(im: Image.Image, k: int = 10, tol: float = 1.5) -> bool:
    """A shifted copy: the gap is filled by repeating the edge row, so a strip
    along one border barely changes from row to row."""
    a = np.asarray(im.convert("L").resize((256, 256)), dtype=np.float32)
    strips = (a[:k], a[-k:][::-1], a[:, :k].T, a[:, -k:][:, ::-1].T)
    return any(float(np.abs(np.diff(s, axis=0)).mean()) < tol for s in strips)


def mirrored(im: Image.Image, seen: list[int]) -> bool:
    """A flipped or half-turned copy of a photo already kept."""
    for v in (im.transpose(Image.FLIP_LEFT_RIGHT), im.transpose(Image.FLIP_TOP_BOTTOM), im.rotate(180)):
        if near(dhash(v), seen, 6):
            return True
    return False


PROGRESS = RAW / "progress.json"
LABEL_OF = {cls: label for label, (cls, _, _) in MAP.items()}


def _from_disk() -> list[dict[str, str]]:
    """The photos an earlier run saved, read back — the run may have stopped
    before writing its index."""
    out = []
    for p in sorted(OUT.rglob("*.jpg")):
        cls = p.parent.name
        with Image.open(p) as im:
            im = im.convert("RGB")
            out.append({"path": str(p.relative_to(ROOT)), "train_class": cls, "target": MAP[LABEL_OF[cls]][1],
                        "crop": "rice", "source": "mendeley:gpsft4c2zy" if p.stem.endswith("_mendeley") else f"hf:{REPO}",
                        "bg": "plain" if is_plain(im) else "field", "dhash": f"{dhash(im):016x}"})
    return out


def _write(rows: list[dict[str, str]]) -> None:
    with CSV_OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    known: set[int] = set()
    for d in EXISTING:
        for p in d.rglob("*.jpg"):
            with Image.open(p) as im:
                known.add(dhash(im))
    known_list = list(known)
    print(f"{len(known)} images already in data/processed", flush=True)

    rows = _from_disk()
    seen: list[int] = [int(r["dhash"], 16) for r in rows]
    done: set[str] = set(json.loads(PROGRESS.read_text())) if PROGRESS.exists() else set()
    taken: Counter[str] = Counter(LABEL_OF[r["train_class"]] for r in rows if r["source"].startswith("hf:"))
    stats: Counter[str] = Counter()
    print(f"{len(rows)} photos already imported; {len(done)} row groups done", flush=True)

    def mark(key: str) -> None:
        done.add(key)
        _write(rows)
        PROGRESS.write_text(json.dumps(sorted(done), indent=1))

    have_mendeley = any(r["source"].startswith("mendeley") for r in rows)
    sources = ([] if have_mendeley else [mendeley_photos()]) + [hf_photos(done, taken, mark)]
    for source in sources:
        for label, data, src in source:
            cls, target, _ = MAP[label]
            try:
                im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            except Exception:  # noqa: BLE001
                stats["unreadable"] += 1
                continue
            h = dhash(im)
            if h in known or near(h, known_list, 3) or near(h, seen, 4):
                stats[f"duplicate {cls}"] += 1
                continue
            # Only on the scraped set: the Sambalpur photos are a curated
            # university set, and the checks misread its soft backgrounds and
            # burst shots of one panicle (18 of 43 rejected, looked at: real).
            if src.startswith("hf:") and (smeared(im) or mirrored(im, seen)):
                stats[f"generated copy {cls}"] += 1
                continue
            seen.append(h)
            im.thumbnail((LONG_SIDE, LONG_SIDE))
            tag = "mendeley" if src.startswith("mendeley") else "vn"
            dst = OUT / cls / f"{len(seen):05d}_{tag}.jpg"
            while dst.exists():
                dst = dst.with_name(f"{dst.stem}b.jpg")
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst, "JPEG", quality=88)
            rows.append({"path": str(dst.relative_to(ROOT)), "train_class": cls, "target": target, "crop": "rice",
                         "source": src, "bg": "plain" if is_plain(im) else "field", "dhash": f"{h:016x}"})
            stats[f"kept {cls}"] += 1

    _write(rows)
    print(f"wrote {CSV_OUT.relative_to(ROOT)}: {len(rows)} new images")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
