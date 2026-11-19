"""One photograph per pest and disease, for the picture beside a field check —
taken only from sets whose licence lets the app show it.

The field checks showed an icon for 34 of the 48 problems: the picture came
from the ICAR set alone, which has no soybean or cotton and no rice blast. The
other sets were downloaded for training, and a set that carried no licence is
used for training only (data/DATASETS.md §5). So a photo is shown from:

  ICAR-IASRI crop disease and pest images   ICAR Data Use Licence
  ASDID (soybean, Zenodo 7304859)           CC0
  Mendeley Data sets checked CC BY 4.0      credited on the landing page

and never from Paddy Doctor, the Hugging Face sets, the farmer-confirmed photos
or the local photographs. A field photo is preferred to a plain backdrop, and
the first in name order is taken so the choice is the same every run.

    .venv/bin/python data/reference_photos.py   -> backend/kb/reference_photos.json
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "backend" / "kb" / "reference_photos.json"
CREDITS_TS = ROOT / "frontend" / "landing" / "src" / "lib" / "photoCredits.ts"

ICAR = {"name": "ICAR-IASRI, Crop Disease and Pest Image Data (data.gov.in)", "licence": "ICAR Data Use License",
        "url": "https://www.data.gov.in/catalog/crop-disease-and-pest-image-data"}
ASDID = {"name": "Wadkar et al., ASDID soybean field images (Zenodo 7304859)", "licence": "CC0",
         "url": "https://zenodo.org/records/7304859"}


def mendeley(dataset_id: str, name: str) -> dict:
    return {"name": f"{name} (Mendeley Data {dataset_id})", "licence": "CC BY 4.0",
            "url": f"https://data.mendeley.com/datasets/{dataset_id}"}


# csv file -> {source value in its rows: credit}. Order is preference order.
SOURCES: list[tuple[str, dict[str, dict]]] = [
    ("icar_images.csv", {"*": ICAR}),
    ("asdid_images.csv", {"asdid": ASDID}),
    ("ricebd_images.csv", {"rice_bd_fungal": mendeley("hx6f852hw4", "Rice Leaf Bacterial and Fungal Disease Dataset")}),
    ("dhan_images.csv", {"dhan_shomadhan": mendeley("znsxdctwtt", "Dhan-Shomadhan rice leaf disease dataset")}),
    ("cotton_images.csv", {"b3jy2p6k8w": mendeley("b3jy2p6k8w", "SAR-CLD-2024 cotton leaf disease dataset"),
                           "74jsdxtmx2": mendeley("74jsdxtmx2", "Cotton Leaf Disease Dataset with Severity Levels"),
                           "t9hgvk2h9p": mendeley("t9hgvk2h9p", "Cotton Leaf Image Dataset for Disease Classification")}),
    ("mendeley2_images.csv", {"mendeley:3myfctrgk3": mendeley("3myfctrgk3", "MLD maize leaf disease dataset"),
                              "mendeley:5wp23rgtpy": mendeley("5wp23rgtpy", "Cotton Aphid Images"),
                              "mendeley:sb4wwjs8bz": mendeley("sb4wwjs8bz", "Multi-format maize leaf image dataset")}),
]


# Read on a contact sheet (19 Nov 2026): the first photo in name order did not
# show the problem for these, so a later one that does is named by its place
# in the same order. Cotton wilt is a whole-plant symptom no leaf photo shows;
# a yellow leaf would read as potassium shortage, so it keeps the icon.
PICK = {"cotton_aphid": 42, "maize_gray_leaf_spot": 248, "soybean_frogeye_leaf_spot": 191}
NONE = {"cotton_wilt"}


def main() -> None:
    targets = [t["id"] for t in json.loads((ROOT / "backend" / "kb" / "targets.json").read_text(encoding="utf-8"))]
    picked: dict[str, dict] = {}
    for fname, credits in SOURCES:
        rows = list(csv.DictReader((PROCESSED / fname).open(encoding="utf-8")))
        for t in targets:
            if t in picked or t in NONE:
                continue
            cands = [r for r in rows if r["target"] == t and (r.get("source", "*") in credits or "*" in credits)]
            cands = [r for r in cands if (ROOT / r["path"]).is_file()]
            if not cands:
                continue
            cands.sort(key=lambda r: (r.get("bg", "field") != "field", r["path"]))
            r = cands[PICK.get(t, 0)] if PICK.get(t, 0) < len(cands) else cands[0]
            credit = credits.get(r.get("source", "*")) or credits["*"]
            picked[t] = {"path": str(Path(r["path"]).relative_to("data/processed")), **credit}
    out = {"_note": ("One photograph per problem for the field-check picture, only from sets whose licence lets the "
                     "app show it (data/reference_photos.py). CC BY sets are credited on the landing page."),
           "photos": dict(sorted(picked.items()))}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    credits = sorted({(p["name"], p["licence"], p["url"]) for p in picked.values()})
    CREDITS_TS.write_text(
        "// Written by data/reference_photos.py: every set a field-check photo comes from.\n"
        "// CC BY 4.0 asks for credit; the landing page footer gives it here.\n"
        "export const PHOTO_CREDITS: { name: string; licence: string; url: string }[] = [\n"
        + "".join(f"  {{ name: {json.dumps(n, ensure_ascii=False)}, licence: {json.dumps(l)}, url: {json.dumps(u)} }},\n"
                  for n, l, u in credits)
        + "]\n", encoding="utf-8")
    print(f"{len(picked)} of {len(targets)} problems have a photo; none for:",
          sorted(set(targets) - set(picked)))


if __name__ == "__main__":
    main()
