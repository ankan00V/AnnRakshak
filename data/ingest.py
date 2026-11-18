"""Turn the raw downloads in data/raw/ into clean, reproducible inputs.

    .venv/bin/python data/ingest.py

Outputs
  data/processed/rainfall/*.csv           tidy IMD rainfall tables
  data/processed/icar_images.csv          one row per ICAR image, with its KB label
  data/processed/icar_640/<class>/*.jpg   images resized to 640 px long side
  backend/kb/imd_rainfall_normals.json    small, committed: monthly normals for the
                                          four Maharashtra subdivisions + district map

data/raw/ and data/processed/ are gitignored; this script is the record of
how one becomes the other. See data/raw/MANIFEST.md for where each raw file
came from.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import xlrd
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
KB = ROOT / "backend" / "kb"

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# IMD's own tables misspell one subdivision and vary capitalisation between
# releases; one canonical spelling keeps joins honest.
SUBDIVISION_FIXES = {"MATATHWADA": "MARATHWADA"}

MAHARASHTRA_SUBDIVISIONS = {
    "KONKAN & GOA": ["Mumbai", "Mumbai Suburban", "Thane", "Palghar", "Raigad", "Ratnagiri", "Sindhudurg"],
    "MADHYA MAHARASHTRA": ["Pune", "Satara", "Sangli", "Kolhapur", "Solapur", "Nashik", "Ahilyanagar",
                           "Dhule", "Nandurbar", "Jalgaon"],
    "MARATHWADA": ["Chhatrapati Sambhajinagar", "Jalna", "Beed", "Latur", "Dharashiv", "Nanded",
                   "Parbhani", "Hingoli"],
    "VIDARBHA": ["Nagpur", "Wardha", "Bhandara", "Gondia", "Chandrapur", "Gadchiroli", "Amravati",
                 "Akola", "Washim", "Buldhana", "Yavatmal"],
}

# ICAR folder -> (training class, knowledge-base target). Fall armyworm larvae
# and fall armyworm damage look nothing alike, so they train as two classes and
# are merged back into one target at inference.
ICAR_CLASSES = {
    "Rice/Disease/01_Bacterial_leaf_blight": ("rice_bacterial_leaf_blight", "rice_bacterial_leaf_blight"),
    "Rice/Disease/02_Brown_spot": ("rice_brown_spot", "rice_brown_spot"),
    "Rice/Disease/03_False_smut": ("rice_false_smut", "rice_false_smut"),
    "Rice/Disease/04_leaf_sheath_blight": ("rice_sheath_blight", "rice_sheath_blight"),
    "Rice/Healthy": ("rice_healthy", "rice_healthy"),
    "Rice/Insect-pests/05_Leaf_folder": ("rice_leaf_folder", "rice_leaf_folder"),
    "Rice/Insect-pests/06_Rice_skipper": ("rice_skipper", "rice_skipper"),
    "Rice/Insect-pests/07_White_stem_borer": ("rice_white_stem_borer", "rice_white_stem_borer"),
    "Rice/Insect-pests/08_Yellow_stem_borer": ("rice_yellow_stem_borer", "rice_yellow_stem_borer"),
    "Maize/Disease/01_maydis_leaf_blight": ("maize_maydis_leaf_blight", "maize_maydis_leaf_blight"),
    "Maize/Disease/02_turcicum_leaf_blight": ("maize_turcicum_leaf_blight", "maize_turcicum_leaf_blight"),
    "Maize/Disease/03_curvularia_leaf_spot": ("maize_curvularia_leaf_spot", "maize_curvularia_leaf_spot"),
    "Maize/Disease/04_sorghum_downy_mildew": ("maize_downy_mildew", "maize_downy_mildew"),
    "Maize/Healthy": ("maize_healthy", "maize_healthy"),
    "Maize/Insect-pests/01_aphid": ("maize_aphid", "maize_aphid"),
    "Maize/Insect-pests/02_fall_armyworm": ("maize_fall_armyworm", "maize_fall_armyworm"),
    "Maize/Insect-pests/03_FAW_symptoms": ("maize_fall_armyworm_damage", "maize_fall_armyworm"),
}
RESIZE_LONG_SIDE = 640


def _sheet(path: Path):
    # data.gov.in .xls exports carry a stream-table quirk that xlrd's strict
    # check reports as "workbook corruption"; the cell data is intact.
    wb = xlrd.open_workbook(str(path), ignore_workbook_corruption=True, logfile=open(os.devnull, "w"))
    return wb.sheet_by_index(0)


def _rows(path: Path) -> tuple[list[str], list[list]]:
    sh = _sheet(path)
    header = [str(c.value).strip() for c in sh.row(0)]
    return header, [[c.value for c in sh.row(i)] for i in range(1, sh.nrows)]


def _num(v):
    if v in ("", None, "NA"):
        return ""
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return ""


def _canon_sub(name: str) -> str:
    n = " ".join(str(name).upper().split())
    return SUBDIVISION_FIXES.get(n, n)


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote {path.relative_to(ROOT)} ({len(rows)} rows)")


def rainfall() -> None:
    src = RAW / "rainfall"
    if not src.exists():
        print("rainfall: data/raw/rainfall missing, skipped")
        return
    out = OUT / "rainfall"
    print("rainfall:")

    # Monthly subdivision tables: 1901-2017 release and the area-weighted 1901-2015 one.
    for name, fname in [
        ("subdivision_monthly_1901_2017", "imd_subdivision_monthly_1901_2017.xls"),
        ("subdivision_area_weighted_monthly_1901_2015", "imd_36_subdivisions_area_weighted_monthly_1901_2015.xls"),
    ]:
        header, rows = _rows(src / fname)
        cols = header[2:]
        tidy = [[_canon_sub(r[0]), int(float(r[1])), *[_num(v) for v in r[2:]]] for r in rows if r[0]]
        _write(out / f"{name}.csv", ["subdivision", "year", *[c.lower() for c in cols]], tidy)

    header, rows = _rows(src / "imd_all_india_area_weighted_monthly_1901_2015.xls")
    _write(out / "all_india_monthly_1901_2015.csv", ["year", *[c.lower() for c in header[2:]]],
           [[int(float(r[1])), *[_num(v) for v in r[2:]]] for r in rows if r[1] != ""])

    # Actual + percentage departure + per-subdivision 1901-2015 statistics.
    header, rows = _rows(src / "imd_subdivision_actual_departure_stats_1901_2015.xls")
    periods = [h.lower() for h in header[3:]]
    stats, yearly = [], []
    for r in rows:
        sub, year, param = _canon_sub(r[0]), str(r[1]), str(r[2]).strip()
        vals = [_num(v) for v in r[3:]]
        if year == "1901-2015":
            stats.append([sub, param, *vals])
        elif param in ("Actual", "Percentage departure"):
            yearly.append([sub, int(float(year)), param, *vals])
    _write(out / "subdivision_stats_1901_2015.csv", ["subdivision", "statistic", *periods], stats)
    _write(out / "subdivision_actual_departure_1901_2015.csv", ["subdivision", "year", "parameter", *periods], yearly)

    # Monsoon (JJAS) actual and departure by homogeneous region, latest release per region.
    tidy = []
    for f in sorted((src / "monsoon_regions").glob("*_1901_2016.xls")):
        region = f.stem.replace("_jjas_1901_2016", "")
        _, rows = _rows(f)
        for r in rows:
            if r[0] == "":
                continue
            tidy.append([region, int(float(r[0])), *[_num(v) for v in r[1:11]]])
    _write(out / "monsoon_regions_jjas_1901_2016.csv",
           ["region", "year", "jun", "jul", "aug", "sep", "jjas",
            "dep_jun_pct", "dep_jul_pct", "dep_aug_pct", "dep_sep_pct", "dep_jjas_pct"], tidy)

    # Committed backend reference: Maharashtra monthly normals (mean, sd) 1901-2015.
    normals: dict = {}
    for sub, param, *vals in stats:
        if sub not in MAHARASHTRA_SUBDIVISIONS or param not in ("Mean", "Standard deviation"):
            continue
        key = "mean" if param == "Mean" else "sd"
        normals.setdefault(sub, {})[key] = dict(zip(periods, vals))
    missing = set(MAHARASHTRA_SUBDIVISIONS) - set(normals)
    if missing:
        sys.exit(f"normals missing for {missing} — check subdivision spelling in the IMD file")
    # Monsoon (JJAS) actual and % departure per year, for the officials' trend chart.
    jjas = periods.index("jjas")
    series: dict = defaultdict(dict)
    for sub, year, param, *vals in yearly:
        if sub in MAHARASHTRA_SUBDIVISIONS:
            series[sub].setdefault(year, {})["actual" if param == "Actual" else "dep_pct"] = vals[jjas]
    ref = {
        "_source": "IMD subdivision-wise rainfall and its departure, 1901-2015 (data.gov.in, "
                   "catalog 'Rainfall in India'). Monthly mean and standard deviation in mm.",
        "subdivisions": normals,
        "jjas_series": {s: [[y, v.get("actual"), v.get("dep_pct")] for y, v in sorted(ys.items())]
                        for s, ys in series.items()},
        "district_to_subdivision": {d: s for s, ds in MAHARASHTRA_SUBDIVISIONS.items() for d in ds},
    }
    (KB / "imd_rainfall_normals.json").write_text(json.dumps(ref, indent=1, ensure_ascii=False))
    print(f"  wrote backend/kb/imd_rainfall_normals.json ({len(normals)} subdivisions)")


def icar_images() -> None:
    src = RAW / "icar_rice_maize"
    if not src.exists():
        print("icar: data/raw/icar_rice_maize missing, skipped")
        return
    print("icar images:")
    rows, seen, counts, dups = [], {}, Counter(), []
    for folder, (cls, target) in ICAR_CLASSES.items():
        d = src / folder
        files = sorted(p for p in d.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
        if not files:
            sys.exit(f"no images in {folder}")
        for p in files:
            digest = hashlib.sha1(p.read_bytes()).hexdigest()
            if digest in seen:
                dups.append((str(p.relative_to(src)), seen[digest]))
                continue
            seen[digest] = str(p.relative_to(src))
            dst = OUT / "icar_640" / cls / (p.stem + ".jpg")
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(p) as im:
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    w, h = im.size
                    im.thumbnail((RESIZE_LONG_SIDE, RESIZE_LONG_SIDE), Image.LANCZOS)
                    im.save(dst, "JPEG", quality=90)
            else:
                with Image.open(p) as im:
                    w, h = im.size
            rows.append([str(dst.relative_to(ROOT)), str(p.relative_to(ROOT)), target.split("_")[0],
                         cls, target, w, h, digest])
            counts[cls] += 1
    _write(OUT / "icar_images.csv",
           ["path", "raw_path", "crop", "train_class", "target", "orig_w", "orig_h", "sha1"], rows)
    for cls, n in sorted(counts.items()):
        print(f"    {cls:32s} {n}")
    if dups:
        print(f"  skipped {len(dups)} exact duplicate image(s):")
        for a, b in dups:
            print(f"    {a}  ==  {b}")


# Extra image sources (received Sep 15, recovered from damaged downloads with
# data/salvage_zip.py). Only classes that map to a KB target are used; lab-style
# photos get background randomisation in training (ml/composite.py).
CD = RAW / "crop_diseases" / "Crop Diseases"
CCMT = RAW / "ccmt" / "Dataset for Crop Pest and Disease Detection" / "Raw Data" / "CCMT Dataset" / "Maize"
EXTRA_CLASSES = [
    # (folder, source, train_class, target, style)
    (CD / "Rice___Leaf_Blast", "crop_diseases", "rice_leaf_blast", "rice_blast", "lab"),
    (CD / "Rice___Neck_Blast", "crop_diseases", "rice_neck_blast", "rice_blast", "lab"),
    (CD / "Rice___Brown_Spot", "crop_diseases", "rice_brown_spot", "rice_brown_spot", "lab"),
    (CD / "Rice___Healthy", "crop_diseases", "rice_healthy", "rice_healthy", "lab"),
    (CD / "Corn___Common_Rust", "crop_diseases", "maize_common_rust", "maize_common_rust", "lab"),
    (CD / "Corn___Northern_Leaf_Blight", "crop_diseases", "maize_turcicum_leaf_blight", "maize_turcicum_leaf_blight", "lab"),
    (CD / "Corn___Healthy", "crop_diseases", "maize_healthy", "maize_healthy", "lab"),
    (CCMT / "fall armyworm", "ccmt", "maize_fall_armyworm_damage", "maize_fall_armyworm", "field"),
    (CCMT / "healthy", "ccmt", "maize_healthy", "maize_healthy", "field"),
]


def _dhash(im: Image.Image) -> str:
    g = np.asarray(im.convert("L").resize((9, 8)), dtype=np.int16)
    return "%016x" % int("".join("1" if b else "0" for b in (g[:, 1:] > g[:, :-1]).flatten()), 2)


def extra_images() -> None:
    """Crop Diseases (Kaggle compilation: PlantVillage maize + white-paper rice
    leaves + neck-blast panicles) and CCMT field maize → data/processed/extra_640
    and extra_images.csv, with a plain-backdrop flag per image."""
    sys.path.insert(0, str(ROOT / "ml"))
    from composite import is_plain  # noqa: PLC0415

    if not CD.exists() and not CCMT.exists():
        print("extra images: data/raw/crop_diseases and data/raw/ccmt missing, skipped")
        return
    print("extra images:")
    rows, seen_sha, seen_d, counts, dups, broken = [], set(), set(), Counter(), 0, 0
    for folder, source, cls, target, style in EXTRA_CLASSES:
        if not folder.exists():
            print(f"    missing {folder.relative_to(RAW)}")
            continue
        for p in sorted(x for x in folder.iterdir() if x.suffix.lower() in (".jpg", ".jpeg", ".png")):
            data = p.read_bytes()
            sha = hashlib.sha1(data).hexdigest()
            try:
                with Image.open(p) as im:
                    im = ImageOps.exif_transpose(im).convert("RGB")
            except Exception:  # noqa: BLE001  unreadable in the source itself
                broken += 1
                continue
            dh = _dhash(im)
            if sha in seen_sha or dh in seen_d:
                dups += 1
                continue
            seen_sha.add(sha)
            seen_d.add(dh)
            dst = OUT / "extra_640" / source / cls / (p.stem.replace(" ", "_") + ".jpg")
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                small = im.copy()
                small.thumbnail((RESIZE_LONG_SIDE, RESIZE_LONG_SIDE), Image.LANCZOS)
                small.save(dst, "JPEG", quality=90)
            bg = "plain" if style == "lab" and is_plain(im) else ("field" if style == "field" else "lab")
            rows.append([str(dst.relative_to(ROOT)), str(p.relative_to(ROOT)), source, target.split("_")[0],
                         cls, target, bg, sha])
            counts[(source, cls, bg)] += 1
    _write(OUT / "extra_images.csv",
           ["path", "raw_path", "source", "crop", "train_class", "target", "bg", "sha1"], rows)
    for (source, cls, bg), n in sorted(counts.items()):
        print(f"    {source:14s} {cls:30s} {bg:6s} {n}")
    print(f"  {len(rows)} images; skipped {dups} exact/near duplicates, {broken} unreadable")


MOSPI_ENV = "https://api.mospi.gov.in/api/env/getEnvStatsRecords"
MOSPI_INDICATORS = {"chemical": 56, "bio": 58}


def mospi_pesticides() -> None:
    """State-wise pesticide consumption from MoSPI eSankhyiki (ENVSTATS).

    The API labels these values "Million tonnes"; the DPPQS source tables they
    come from are in MT (metric tonnes, technical grade), and 8,719 million
    tonnes in one state is physically impossible, so the unit is recorded as
    tonnes with that correction noted."""
    import subprocess

    print("mospi pesticides:")
    out: dict = {
        "_source": "MoSPI eSankhyiki ENVSTATS indicators 56 (chemical pesticides) and 58 (bio-pesticide "
                   "formulations), originally DPPQS. api.mospi.gov.in",
        "_unit_note": "API labels the unit 'Million tonnes'; the DPPQS source is MT (metric tonnes, technical "
                      "grade). Stored as tonnes.",
        "states": {},
    }
    for kind, code in MOSPI_INDICATORS.items():
        # curl, not Python's ssl: api.mospi.gov.in's TLS setup times out the
        # handshake with Python/OpenSSL 3 while curl negotiates fine.
        rows, err = None, None
        for _attempt in range(3):
            try:
                raw = subprocess.run(
                    ["curl", "-s", "--max-time", "40", f"{MOSPI_ENV}?indicator_code={code}"],
                    capture_output=True, check=True, timeout=60,
                ).stdout
                rows = json.loads(raw)["data"]
                break
            except Exception as exc:  # network is optional for ingest
                err = exc
        if rows is None:
            print(f"  indicator {code} unavailable ({err}); skipped")
            return
        for row in rows:
            state, val = row.get("state"), row.get("value")
            if not state or val in (None, ""):
                continue
            try:
                v = float(val)
            except ValueError:
                continue
            out["states"].setdefault(state, {}).setdefault(kind, []).append([row["year"], v])
    for s in out["states"].values():
        for k in s:
            s[k].sort()
    (KB / "mospi_pesticides.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    mh = out["states"].get("Maharashtra", {})
    print(f"  wrote backend/kb/mospi_pesticides.json ({len(out['states'])} states; "
          f"Maharashtra chemical {mh.get('chemical', [])[-1:]}, bio {mh.get('bio', [])[-1:]})")


PPQS = "https://ppqs.gov.in/sites/default/files/"
# The DPPQS Statistical Database (ppqs.gov.in/statistical-database): the
# primary source the MoSPI series above republishes, two years further on.
PPQS_FILES = {
    "chemical": "03_state-wise_consumption_of_chemical_pesticides_0.xlsx",
    "bio": "04_state-wise_consumption_of_bio-pesticides_0.xlsx",
    "demand_chemical": "01_state-wise_demand_of_chemical_pesticides_0.xlsx",
    "demand_bio": "02_state-wise_demand_of_bio-pesticides_0.xlsx",
    "by_pesticide": "10_pesticide-wise_consumption_of_indigenuous_pesticides_0.xlsx",
}
PPQS_GROUPS = {"i": "Insecticides", "f": "Fungicides", "h": "Weedicides", "bp": "Bio-pesticides",
               "pgr": "Plant growth regulators", "r": "Rodenticides", "misc": "Miscellaneous"}
# DPPQS spellings that differ from the MoSPI names the dashboard keys on.
PPQS_STATE_ALIASES = {"pondicherry": "puducherry", "orissa": "odisha",
                      "a and n islands": "andaman and nicobar islands", "andaman and nicobar": "andaman and nicobar islands",
                      "andaman nicobar islands": "andaman and nicobar islands",
                      "j and k": "jammu and kashmir", "nct of delhi": "delhi"}


def _state_key(name: str) -> str:
    import re  # noqa: PLC0415
    k = re.sub(r"[^a-z ]+", " ", str(name).lower().replace("&", " and "))
    k = " ".join(k.split())
    return PPQS_STATE_ALIASES.get(k, k)


def _year(h) -> str | None:
    """'2022-23 ', '2025-26*' and 'Projected Demand for 2026-27' all name a year."""
    import re  # noqa: PLC0415
    m = re.search(r"(20\d\d)\s*-\s*(\d\d)", str(h or ""))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _ppqs_value(v):
    """A number, or None for 'NR' (not reported), blanks and dashes. A state
    that did not report is not a state that used nothing."""
    if isinstance(v, (int, float)):
        return round(float(v), 3)
    try:
        return round(float(str(v).replace(",", "").strip()), 3)
    except ValueError:
        return None


def ppqs_pesticides() -> None:
    """State-wise pesticide use and demand, and pesticide-wise use, from the
    DPPQS Statistical Database (2021-22 to 2025-26), into
    backend/kb/ppqs_pesticides.json.

    Kept apart from the MoSPI file, which carries the years before 2021-22:
    the dashboard joins the two, DPPQS winning where they overlap (they agree:
    Maharashtra 2023-24 is 8,719 t in both). Demand is in tonnes of
    formulation while use mixes technical grade and formulation, so the two are
    stored side by side and never subtracted."""
    import subprocess  # noqa: PLC0415
    from datetime import date  # noqa: PLC0415

    import openpyxl  # noqa: PLC0415

    print("ppqs pesticides:")
    raw = RAW / "ppqs"
    raw.mkdir(parents=True, exist_ok=True)
    for name in PPQS_FILES.values():
        dst = raw / name
        try:
            subprocess.run(["curl", "-sfL", "--max-time", "40", "-A", "Mozilla/5.0", "-o", str(dst), PPQS + name],
                           check=True, timeout=60)
        except Exception as exc:  # network is optional for ingest: keep the last copy
            print(f"  {name}: download failed ({exc}); {'using the copy on disk' if dst.exists() else 'skipped'}")
    if not all((raw / n).exists() for n in PPQS_FILES.values()):
        print("  not every DPPQS sheet is on disk; backend/kb/ppqs_pesticides.json left as it was")
        return

    mospi = json.loads((KB / "mospi_pesticides.json").read_text()) if (KB / "mospi_pesticides.json").exists() else {}
    known = {_state_key(n): n for n in mospi.get("states", {})}

    def table(name: str):
        ws = openpyxl.load_workbook(raw / name, read_only=True, data_only=True).worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True) if any(c not in (None, "") for c in r)]
        head = next(i for i, r in enumerate(rows) if any(_year(c) for c in r))
        cols = [(j, _year(c), "projected" in str(c).lower()) for j, c in enumerate(rows[head]) if _year(c)]
        return rows[head + 1:], cols

    states: dict = {}
    unmatched: set[str] = set()
    national: dict = {}
    for kind in ("chemical", "bio", "demand_chemical", "demand_bio"):
        body, cols = table(PPQS_FILES[kind])
        for r in body:
            label = next((c for c in r[:3] if isinstance(c, str) and c.strip()), "")
            if "total" in label.lower():
                if "grand" in label.lower() or label.strip().lower() == "total":
                    national[kind] = [[y, v] for j, y, proj in cols if not proj and (v := _ppqs_value(r[j])) is not None]
                continue
            if not isinstance(r[0], (int, float)) or not label:
                continue  # notes, sub-headings, sub-totals
            key = _state_key(label)
            name = known.get(key)
            if name is None:
                unmatched.add(label.strip())
                name = " ".join(label.split())
            entry = states.setdefault(name, {})
            for j, y, proj in cols:
                v = _ppqs_value(r[j])
                if v is None:
                    continue
                if proj:
                    entry.setdefault("projected", {"year": y})[kind.replace("demand_", "")] = v
                else:
                    entry.setdefault(kind, []).append([y, v])

    body, cols = table(PPQS_FILES["by_pesticide"])
    pesticides, by_group = [], defaultdict(lambda: defaultdict(float))
    for r in body:
        if not isinstance(r[0], (int, float)) or not isinstance(r[1], str):
            continue
        group = str(r[2] or "").strip().lower()
        series = [[y, v] for j, y, _ in cols if (v := _ppqs_value(r[j])) is not None]
        pesticides.append({"name": " ".join(r[1].split()), "group": group, "series": series})
        for y, v in series:
            by_group[group][y] += v

    out = {
        "_source": "Directorate of Plant Protection, Quarantine & Storage (DPPQS), Statistical Database, "
                   "ppqs.gov.in/statistical-database: state-wise consumption and demand of chemical and "
                   "bio-pesticides, and pesticide-wise consumption of indigenous pesticides, from States/UTs' "
                   "reports on inputs of plant protection.",
        "_fetched": date.today().isoformat(),
        "_units": {
            "chemical": "tonnes (technical grade/formulation, as reported by states)",
            "bio": "tonnes of formulation",
            "demand_chemical": "tonnes of formulation (estimated)",
            "demand_bio": "tonnes of formulation (estimated)",
            "by_pesticide": "tonnes (technical grade/formulation)",
        },
        "_notes": [
            "NR (not reported) is left out, never counted as zero; national totals are DPPQS's own.",
            "Demand is in tonnes of formulation and use mixes technical grade and formulation, so the two "
            "are not compared.",
            "Pesticide-wise 2025-26 covers 16 States/UTs (Agenda Report on Plant Protection, kharif 2026); "
            "2024-25 is the latest complete year.",
        ],
        "partial_years": {"by_pesticide": ["2025-26"]},
        "groups": PPQS_GROUPS,
        "national": {
            **{k: v for k, v in national.items()},
            "by_group": {g: sorted([y, round(v, 1)] for y, v in ys.items()) for g, ys in by_group.items()},
        },
        "states": dict(sorted(states.items())),
        "pesticides": pesticides,
    }
    (KB / "ppqs_pesticides.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    mh = states.get("Maharashtra", {})
    print(f"  wrote backend/kb/ppqs_pesticides.json ({len(states)} states, {len(pesticides)} pesticides; "
          f"Maharashtra chemical {mh.get('chemical', [])[-1:]}, projected {mh.get('projected')})")
    if unmatched:
        print(f"  not in the MoSPI list, kept under DPPQS's spelling: {', '.join(sorted(unmatched))}")


def _clean_name(s: str) -> str:
    """Repository text is double-encoded in places (Â“ Â” Â• &#8722;); compare on
    plain words only."""
    import html  # noqa: PLC0415
    import re  # noqa: PLC0415

    s = html.unescape(s)
    s = re.sub(r"[^0-9A-Za-z]+", " ", s)
    return " ".join(s.lower().split())


def icar_technologies() -> None:
    """Cross-check backend/kb/icar_technologies.json against the repository CSV.
    The KB entries are curated (linked to our targets, summarised, translated);
    this makes sure every one still names a real row of the source."""
    import csv  # noqa: PLC0415

    kb_file = KB / "icar_technologies.json"
    src = sorted((RAW / "icar_technologies").glob("*.csv")) if (RAW / "icar_technologies").exists() else []
    if not src:
        print("  ICAR technologies: no CSV in data/raw/icar_technologies/ — KB entries not cross-checked "
              "(see data/MANUAL_DOWNLOADS.md)")
        return
    names = set()
    for f in src:
        with f.open(encoding="utf-8", errors="replace", newline="") as fh:
            for row in csv.DictReader(fh):
                names.add(_clean_name(row.get("Technology Name", "")))
    kb = json.loads(kb_file.read_text(encoding="utf-8"))
    missing = [t["id"] for t in kb["technologies"] if _clean_name(t["source_name"]) not in names]
    print(f"  ICAR technologies: {len(names)} rows in source; "
          f"{len(kb['technologies']) - len(missing)}/{len(kb['technologies'])} KB entries matched"
          + (f"; NOT FOUND: {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    rainfall()
    icar_images()
    extra_images()
    mospi_pesticides()
    ppqs_pesticides()
    icar_technologies()
