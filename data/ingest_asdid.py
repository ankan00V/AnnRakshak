"""ASDID: 9,648 soybean field photos from Alabama, eight categories.

Every soybean photo we train on today comes from one Indian dataset
(MH-SoyaHealthVision), and it shows: frogeye leaf spot has 169 photos, healthy
204, and the held-out recall on frogeye and septoria sits under the 0.70 bar
that keeps soybean switched off in the app. A model that has only ever seen one
camera, one district and one season learns the dataset, not the disease.

ASDID is the Auburn soybean disease image dataset (CC0): 2020-21 seasons, three
Alabama research stations, a DSLR and a phone, leaves shot on the plant, on
trimmed grass and on white card. Three of its categories refill classes we
already have; five are problems the app could not name before and now can, with
advisories written into backend/kb alongside this import.

  Wadkar et al., Computers and Electronics in Agriculture 203 (2022) 107449
  https://doi.org/10.1016/j.compag.2022.107449  ·  Zenodo record 7304859

Zenodo throttles a single connection to ~0.4 MB/s, so each zip is pulled in
sixteen parallel byte ranges, imported, and deleted before the next one starts:
peak disk stays at one zip (8.4 GB) instead of the 42 GB record.

    .venv/bin/python data/ingest_asdid.py            # all eight categories
    .venv/bin/python data/ingest_asdid.py frogeye healthy
      -> data/processed/asdid_640/<class>/*.jpg
         data/processed/asdid_images.csv  (path, train_class, target, crop, source, bg, dhash)
"""

from __future__ import annotations

import csv
import io
import sys
import threading
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "data"))
from composite import is_plain  # noqa: E402
from ingest_more import dhash, near  # noqa: E402

RAW = ROOT / "data" / "raw" / "asdid"
OUT = ROOT / "data" / "processed" / "asdid_640"
CSV_OUT = ROOT / "data" / "processed" / "asdid_images.csv"
EXISTING = [ROOT / "data" / "processed" / d for d in ("icar_640", "extra_640", "more_640", "paddy_640")]
BASE = "https://zenodo.org/api/records/7304859/files/{}.zip/content"
LONG_SIDE = 640
SOURCE = "asdid"
WORKERS = 16
FIELDS = ["path", "train_class", "target", "crop", "source", "bg", "dhash"]

# ASDID category -> (our training class, our KB target).  Biggest need first:
# frogeye and healthy are the two classes holding soybean back.
USE = {
    "frogeye": ("soybean_frogeye_leaf_spot", "soybean_frogeye_leaf_spot"),
    "healthy": ("soybean_healthy", "soybean_healthy"),
    "soybean_rust": ("soybean_rust", "soybean_rust"),
    # problems the app could not name before this import (advisories: backend/kb)
    "target_spot": ("soybean_target_spot", "soybean_target_spot"),
    "cercospora_leaf_blight": ("soybean_cercospora_leaf_blight", "soybean_cercospora_leaf_blight"),
    "downey_mildew": ("soybean_downy_mildew", "soybean_downy_mildew"),
    "bacterial_blight": ("soybean_bacterial_blight", "soybean_bacterial_blight"),
    "potassium_deficiency": ("soybean_potassium_deficiency", "soybean_potassium_deficiency"),
}


def fetch(category: str) -> Path:
    """Download one category zip in parallel byte ranges; it is named .zip only once whole."""
    dst = RAW / f"{category}.zip"
    if dst.exists():  # only a finished download is ever named .zip
        print(f"  {category}.zip already here ({dst.stat().st_size / 1e9:.2f} GB)")
        return dst
    url = BASE.format(category)
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as r:
        total = int(r.headers["Content-Length"])
        url = r.url  # follow the redirect once so every worker hits the same file
    part = dst.with_suffix(".zip.part")
    part.parent.mkdir(parents=True, exist_ok=True)
    with part.open("wb") as f:
        f.truncate(total)
    span = total // WORKERS + 1
    done = [0] * WORKERS
    lock = threading.Lock()

    def pull(i: int) -> None:
        start, end = i * span, min((i + 1) * span, total) - 1
        while start <= end:
            req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r, part.open("r+b") as f:
                    f.seek(start)
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                        start += len(chunk)
                        with lock:
                            done[i] += len(chunk)
            except Exception as e:  # noqa: BLE001  Zenodo drops long connections; pick up where we stopped
                print(f"    worker {i}: {type(e).__name__}, resuming at {start}", flush=True)

    threads = [threading.Thread(target=pull, args=(i,), daemon=True) for i in range(WORKERS)]
    for t in threads:
        t.start()
    pending = threads
    while pending:
        pending[0].join(timeout=30)
        pending = [t for t in pending if t.is_alive()]
        with lock:
            got = sum(done)
        print(f"    {category}: {got / 1e9:.2f}/{total / 1e9:.2f} GB", flush=True)
    if sum(done) < total:
        raise SystemExit(f"{category}: download stopped {(total - sum(done)) / 1e6:.0f} MB short — run it again")
    part.rename(dst)
    return dst


def known_hashes() -> tuple[dict[int, str], list[int]]:
    known: dict[int, str] = {}
    for d in EXISTING:
        for p in d.rglob("*.jpg"):
            with Image.open(p) as im:
                known[dhash(im)] = str(p.relative_to(ROOT))
    return known, list(known)


def main() -> None:
    wanted = [c for c in (sys.argv[1:] or USE) if c in USE]
    if len(wanted) != len(sys.argv[1:] or wanted):
        raise SystemExit(f"unknown category; pick from {', '.join(USE)}")
    rows: list[dict[str, str]] = []
    if CSV_OUT.exists():
        rows = list(csv.DictReader(CSV_OUT.open()))
        already = {r["train_class"] for r in rows}
        wanted = [c for c in wanted if USE[c][0] not in already]
        print(f"{len(rows)} images already imported; {len(wanted)} categories left")
    known, known_list = known_hashes()
    print(f"{len(known)} images already in data/processed")

    for category in wanted:
        cls, target = USE[category]
        print(f"\n{category} -> {cls}", flush=True)
        zip_path = fetch(category)
        seen: list[int] = []
        stats: Counter[str] = Counter()
        with zipfile.ZipFile(zip_path) as zf:
            names = sorted(n for n in zf.namelist() if n.lower().endswith((".jpg", ".jpeg")) and "__MACOSX" not in n)
            for i, name in enumerate(names, 1):
                try:
                    im = ImageOps.exif_transpose(Image.open(io.BytesIO(zf.read(name)))).convert("RGB")
                except Exception:  # noqa: BLE001  unreadable file
                    stats["unreadable"] += 1
                    continue
                h = dhash(im)
                if h in known or near(h, known_list, 3) or near(h, seen):
                    stats["duplicate"] += 1
                    continue
                seen.append(h)
                im.thumbnail((LONG_SIDE, LONG_SIDE))
                dst = OUT / cls / f"{len(seen):05d}_{Path(name).stem[:40]}.jpg"
                dst.parent.mkdir(parents=True, exist_ok=True)
                im.save(dst, "JPEG", quality=88)
                rows.append({"path": str(dst.relative_to(ROOT)), "train_class": cls, "target": target,
                             "crop": "soybean", "source": SOURCE, "bg": "plain" if is_plain(im) else "field",
                             "dhash": f"{h:016x}"})
                stats["kept"] += 1
                if i % 400 == 0:
                    print(f"    {i}/{len(names)} read", flush=True)
        zip_path.unlink()  # 8 GB we will not need again; the resized copies are the dataset now
        with CSV_OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"  {cls}: {dict(stats)}", flush=True)

    print(f"\nwrote {CSV_OUT.relative_to(ROOT)}: {len(rows)} images")
    kept = Counter(r["train_class"] for r in rows)
    field = Counter(r["train_class"] for r in rows if r["bg"] == "field")
    for cls in sorted(kept):
        print(f"  {cls:34s} {kept[cls]:5d}  ({field[cls]} field)")


if __name__ == "__main__":
    main()
