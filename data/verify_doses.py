"""Check every chemical rung in backend/kb/advisories.json against the CIB&RC
'Major Uses of Pesticides' lists (Registered under the Insecticides Act, 1968),
and record the registration each one rests on.

The lists (ppqs.gov.in/divisions/cib-rc/major-uses-of-pesticides, as on
30.09.2026) are read into data/raw/cibrc/ by `--fetch`. Each rung was matched by
hand to its row — crop, pest, formulation dose per hectare, water per hectare,
waiting period — because the PDFs' tables do not survive text extraction
cleanly enough to trust a parser with a dose. The decisions are the table
below; this script applies them and is the record of why.

A rung whose product is not registered for that crop and that pest is removed,
or replaced by a product that is. Nothing here is advice the list does not
carry. Doses are converted to the app's form: product per litre of water at
the registered water volume, rounded to a measurable amount.

    .venv/bin/python data/verify_doses.py [--fetch]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "backend" / "kb"
RAW = ROOT / "data" / "raw" / "cibrc"
LISTS = {
    "I": ("MUP (insecticide)  30.09.2026.pdf", "MUP%20%28insecticide%29%20%2030.09.2026.pdf"),
    "F": ("Fungicide MUP  as on 30.09.2026.pdf", "Fungicide%20MUP%20%20as%20on%2030.09.2026.pdf"),
}
SOURCE = {"I": "CIB&RC Major Uses of Pesticides — Insecticides, as on 30.09.2026",
          "F": "CIB&RC Major Uses of Pesticides — Fungicides, as on 30.09.2026"}

# New products, each registered for the use it is added for.
NEW_PESTICIDES = {
    "flutriafol_23sc": {"name": "Flutriafol 23% SC", "class": "fungicide",
                        "aliases": ["flutriafol", "फ्लूट्रियाफोल", "फ्लुट्रियाफॉल"]},
    "mancozeb_hexaconazole_wg": {"name": "Mancozeb 68% + Hexaconazole 4% WG", "class": "fungicide",
                                 "aliases": ["mancozeb hexaconazole", "mancozeb + hexaconazole",
                                             "hexaconazole mancozeb", "hexaconazole + mancozeb"]},
    "copper_hydroxide_53_8df": {"name": "Copper hydroxide 53.8% DF", "class": "fungicide",
                                "aliases": ["copper hydroxide 53.8", "copper hydroxide 53.8% df"]},
    "buprofezin_70df": {"name": "Buprofezin 70% DF", "class": "insecticide",
                        "aliases": ["buprofezin 70", "buprofezin 70% df"]},
    "kresoxim_methyl_44_3sc": {"name": "Kresoxim-methyl 44.3% SC", "class": "fungicide",
                               "aliases": ["kresoxim-methyl", "kresoxim methyl", "क्रेसोक्सिम मिथाइल",
                                           "क्रेसॉक्सिम मिथाइल"]},
    "pyriproxyfen_bifenthrin_ec": {"name": "Pyriproxyfen 10% + Bifenthrin 10% EC", "class": "insecticide",
                                   "aliases": ["pyriproxyfen bifenthrin", "pyriproxyfen + bifenthrin"]},
    "thiamethoxam_lambda_zc": {"name": "Thiamethoxam 12.6% + Lambda-cyhalothrin 9.5% ZC", "class": "insecticide",
                               "aliases": ["thiamethoxam lambda", "thiamethoxam + lambda-cyhalothrin",
                                           "thiamethoxam lambda cyhalothrin", "thiamethoxam + lambda cyhalothrin"]},
    "pyraclostrobin_20wg": {"name": "Pyraclostrobin 20% WG", "class": "fungicide",
                            "aliases": ["pyraclostrobin", "पायराक्लोस्ट्रोबिन"]},
    "azoxystrobin_mancozeb_wg": {"name": "Azoxystrobin 8.3% + Mancozeb 66.7% WG", "class": "fungicide",
                                 "aliases": ["azoxystrobin mancozeb", "azoxystrobin + mancozeb"]},
}


def reg(lst, crop, pest, per_ha, water, wait):
    return {"source": SOURCE[lst], "crop": crop, "pest": pest, "formulation_per_ha": per_ha,
            "water_l_per_ha": water, "waiting_days": wait}


# (target, ingredient as it stands) -> decision.
#   ("keep", registration, {changes})          registered: verified, dose put right
#   ("swap", new ingredient, registration, {changes})
#   ("drop", reason)                           not registered for this crop and pest
D = {
    ("rice_blast", "tricyclazole_75wp"): ("keep", reg("F", "Paddy (Rice)", "Blast", "300–400 g", "500", 30), {}),
    ("rice_blast", "isoprothiolane_40ec"): ("keep", reg("F", "Rice (Paddy)", "Blast", "750 ml", "500–1000", 60), {}),
    ("rice_brown_spot", "mancozeb_75wp"): ("swap", "flutriafol_23sc",
        reg("F", "Rice", "Sheath blight & brown spot", "600 ml", "500", 24),
        {"dose_per_litre": 1.2, "dose_unit": "ml", "water_l_per_acre": 200}),
    ("rice_brown_spot", "propiconazole_25ec"): ("swap", "mancozeb_hexaconazole_wg",
        reg("F", "Rice", "Blast, sheath blight, brown spot, grain discolouration", "1250 g", "500", 30),
        {"dose_per_litre": 2.5, "dose_unit": "g", "water_l_per_acre": 200}),
    ("rice_bacterial_leaf_blight", "copper_oxychloride_50wp"): ("swap", "copper_hydroxide_53_8df",
        reg("F", "Rice (Paddy)", "False smut, bacterial leaf blight", "1500 g", "500", 10),
        {"dose_per_litre": 3.0, "dose_unit": "g", "water_l_per_acre": 200}),
    ("rice_sheath_blight", "hexaconazole_5ec"): ("keep", reg("F", "Rice (Paddy)", "Blast, sheath blight", "1000 ml", "500", 40), {}),
    ("rice_sheath_blight", "validamycin_3l"): ("keep", reg("F", "Rice (Paddy)", "Sheath blight", "2000 ml", "750", 14),
        {"dose_per_litre": 2.7, "water_l_per_acre": 300}),
    ("rice_false_smut", "propiconazole_25ec"): ("drop", "Propiconazole 25% EC is registered on rice for sheath blight only."),
    ("rice_false_smut", "copper_hydroxide_77wp"): ("keep", reg("F", "Rice (Paddy)", "False smut", "2000 g", "750", None),
        {"dose_per_litre": 2.7, "water_l_per_acre": 300, "timing_from": ("rice_false_smut", "propiconazole_25ec")}),
    ("rice_tungro", "imidacloprid_17_8sl"): ("keep", reg("I", "Paddy (Rice)", "Green leaf hopper (the tungro vector), plant hoppers", "100–125 ml", "500–700", 40), {}),
    ("rice_leaf_folder", "chlorantraniliprole_18_5sc"): ("keep", reg("I", "Rice", "Stem borer, leaf folder", "150 ml", "500", 47), {}),
    ("rice_yellow_stem_borer", "chlorantraniliprole_0_4gr"): ("keep", reg("I", "Rice (Paddy)", "Yellow stem borer, leaf folder", "10 kg", "broadcast", 53), {}),
    ("rice_brown_planthopper", "pymetrozine_50wg"): ("keep", reg("I", "Paddy (Rice)", "Brown plant hopper", "300 g", "500", 19), {}),
    ("rice_brown_planthopper", "buprofezin_25sc"): ("swap", "buprofezin_70df",
        reg("I", "Rice", "Brown plant hopper", "250 g", "500", 24),
        {"dose_per_litre": 0.5, "dose_unit": "g", "water_l_per_acre": 200}),
    ("maize_turcicum_leaf_blight", "mancozeb_75wp"): ("keep", reg("F", "Maize", "Leaf blight, downy mildew", "1.5–2 kg", "750", None),
        {"water_l_per_acre": 300}),
    ("maize_turcicum_leaf_blight", "propiconazole_25ec"): ("swap", "kresoxim_methyl_44_3sc",
        reg("F", "Maize", "Turcicum leaf blight, rust", "500 ml", "500", 25),
        {"dose_per_litre": 1.0, "dose_unit": "ml", "water_l_per_acre": 200}),
    ("maize_maydis_leaf_blight", "mancozeb_75wp"): ("keep", reg("F", "Maize", "Leaf blight, downy mildew", "1.5–2 kg", "750", None),
        {"water_l_per_acre": 300}),
    ("maize_common_rust", "mancozeb_75wp"): ("swap", "kresoxim_methyl_44_3sc",
        reg("F", "Maize", "Turcicum leaf blight, rust", "500 ml", "500", 25),
        {"dose_per_litre": 1.0, "dose_unit": "ml", "water_l_per_acre": 200}),
    ("maize_common_rust", "propiconazole_25ec"): ("drop", "Propiconazole 25% EC is not registered on maize."),
    ("maize_banded_leaf_sheath_blight", "validamycin_3l"): ("drop", "Validamycin 3% L is registered on rice only; no foliar spray is registered on maize for banded leaf and sheath blight."),
    ("maize_downy_mildew", "metalaxyl_mancozeb_72wp"): ("swap", "mancozeb_75wp",
        reg("F", "Maize", "Leaf blight, downy mildew", "1.5–2 kg", "750", None),
        {"dose_per_litre": 2.5, "dose_unit": "g", "water_l_per_acre": 300}),
    ("maize_fall_armyworm", "emamectin_benzoate_5sg"): ("drop", "Emamectin benzoate 5% SG is not registered on maize."),
    ("maize_fall_armyworm", "chlorantraniliprole_18_5sc"): ("keep", reg("I", "Maize", "Stem borers, fall armyworm", "200 ml", "500", 10),
        {"timing_from": ("maize_fall_armyworm", "emamectin_benzoate_5sg")}),
    ("maize_fall_armyworm", "spinetoram_11_7sc"): ("drop", "Spinetoram 11.7% SC is not registered on maize."),
    ("maize_stem_borer", "chlorantraniliprole_18_5sc"): ("keep", reg("I", "Maize", "Stem borers, fall armyworm", "200 ml", "500", 10),
        {"dose_per_litre": 0.4}),
    ("cotton_pink_bollworm", "profenofos_50ec"): ("keep", reg("I", "Cotton", "Bollworm", "1500–2000 ml", "500–1000", 15),
        {"dose_per_litre": 3.0}),
    ("cotton_pink_bollworm", "thiodicarb_75wp"): ("keep", reg("I", "Cotton", "Bollworms", "1000 g", "500", 30), {}),
    ("cotton_american_bollworm", "emamectin_benzoate_5sg"): ("keep", reg("I", "Cotton", "Boll worms", "190–220 g", "500", 10), {}),
    ("cotton_american_bollworm", "indoxacarb_14_5sc"): ("keep", reg("I", "Cotton", "Bollworm", "500 ml", "600–1000", 16),
        {"dose_per_litre": 0.8, "water_l_per_acre": 250}),
    ("cotton_whitefly", "pyriproxyfen_10ec"): ("keep", reg("I", "Cotton", "Whitefly", "500–700 ml", "500", 50), {}),
    ("cotton_whitefly", "diafenthiuron_50wp"): ("keep", reg("I", "Cotton", "Whiteflies, aphids, thrips, jassids", "600 g", "500–1000", 21), {}),
    ("cotton_jassid", "flonicamid_50wg"): ("keep", reg("I", "Cotton", "Aphids, jassids, thrips, whiteflies", "150 g", "500", 25), {}),
    ("soybean_yellow_mosaic", "thiamethoxam_25wg"): ("swap", "pyriproxyfen_bifenthrin_ec",
        reg("I", "Soybean", "Whitefly (the yellow mosaic vector)", "1000 ml", "500", 35),
        {"dose_per_litre": 2.0, "dose_unit": "ml", "water_l_per_acre": 200}),
    ("soybean_girdle_beetle", "thiacloprid_21_7sc"): ("keep", reg("I", "Soybean", "Girdle beetle", "750 ml", "500", 17), {}),
    ("soybean_girdle_beetle", "chlorantraniliprole_18_5sc"): ("keep", reg("I", "Soybean", "Girdle beetle, tobacco caterpillar, green semilooper, stem fly", "150 ml", "500–750", 22), {}),
    ("soybean_tobacco_caterpillar", "chlorantraniliprole_18_5sc"): ("keep", reg("I", "Soybean", "Girdle beetle, tobacco caterpillar, green semilooper, stem fly", "150 ml", "500–750", 22), {}),
    ("soybean_rust", "propiconazole_25ec"): ("keep", reg("F", "Soybean", "Rust (Phakopsora pachyrhizi)", "500 ml", "500", 26), {}),
    ("soybean_rust", "hexaconazole_5ec"): ("keep", reg("F", "Soybean", "Rust", "0.1% (100 ml / 100 L)", "as required", 30),
        {"dose_per_litre": 1.0}),
    ("rice_white_stem_borer", "chlorantraniliprole_0_4gr"): ("swap", "chlorantraniliprole_18_5sc",
        reg("I", "Rice", "Stem borer, leaf folder", "150 ml", "500", 47),
        {"dose_per_litre": 0.3, "dose_unit": "ml", "water_l_per_acre": 200, "dose_basis": None}),
    ("maize_curvularia_leaf_spot", "mancozeb_75wp"): ("drop", "No product is registered on maize for Curvularia leaf spot."),
    ("maize_aphid", "thiamethoxam_25wg"): ("swap", "thiamethoxam_lambda_zc",
        reg("I", "Maize", "Aphid, shoot fly, stem borer", "125 ml", "500", 42),
        {"dose_per_litre": 0.25, "dose_unit": "ml", "water_l_per_acre": 200}),
    ("cotton_bacterial_blight", "copper_oxychloride_50wp"): ("drop", "Copper oxychloride 50% WP is not registered on cotton; for bacterial blight only seed treatments are registered."),
    ("cotton_leaf_curl", "pyriproxyfen_10ec"): ("keep", reg("I", "Cotton", "Whitefly (the leaf curl vector)", "500–700 ml", "500", 50), {}),
    ("cotton_leaf_curl", "diafenthiuron_50wp"): ("keep", reg("I", "Cotton", "Whiteflies (the leaf curl vector), aphids, thrips, jassids", "600 g", "500–1000", 21), {}),
    ("cotton_wilt", "carbendazim_50wp"): ("drop", "Carbendazim 50% WP is registered on cotton for leaf spot only; for wilt only seed treatments are registered."),
    ("cotton_alternaria_leaf_spot", "mancozeb_75wp"): ("drop", "Mancozeb 75% WP is not registered on cotton."),
    ("cotton_alternaria_leaf_spot", "propiconazole_25ec"): ("keep", reg("F", "Cotton", "Alternaria leaf spot", "500 ml", "500", 23),
        {"timing_from": ("cotton_alternaria_leaf_spot", "mancozeb_75wp")}),
    ("cotton_aphid", "flonicamid_50wg"): ("keep", reg("I", "Cotton", "Aphids, jassids, thrips, whiteflies", "150 g", "500", 25), {}),
    ("soybean_frogeye_leaf_spot", "hexaconazole_5ec"): ("swap", "pyraclostrobin_20wg",
        reg("F", "Soybean", "Frog eye leaf spot (Cercospora)", "375–500 g", "500", 26),
        {"dose_per_litre": 0.8, "dose_unit": "g", "water_l_per_acre": 200}),
    ("soybean_septoria_brown_spot", "carbendazim_50wp"): ("drop", "Carbendazim 50% WP is not registered on soybean."),
    ("maize_gray_leaf_spot", "propiconazole_25ec"): ("drop", "Propiconazole 25% EC is not registered on maize."),
    ("maize_gray_leaf_spot", "mancozeb_75wp"): ("drop", "Mancozeb 75% WP is registered on maize for leaf blight and downy mildew, not gray leaf spot."),
    ("rice_hispa", "chlorpyrifos_20ec"): ("keep", reg("I", "Paddy (Rice)", "Hispa", "1250 ml", "500–1000", None), {}),
    ("rice_bacterial_leaf_streak", "copper_oxychloride_50wp"): ("drop", "Copper oxychloride 50% WP is not registered on rice; no spray is registered for bacterial leaf streak."),
    ("rice_downy_mildew", "metalaxyl_mancozeb_72wp"): ("drop", "Metalaxyl 8% + Mancozeb 64% WP is not registered on rice."),
    ("soybean_target_spot", "propiconazole_25ec"): ("drop", "Propiconazole 25% EC is registered on soybean for rust only."),
    ("soybean_cercospora_leaf_blight", "hexaconazole_5ec"): ("swap", "azoxystrobin_mancozeb_wg",
        reg("F", "Soybean", "Cercospora leaf spot, Myrothecium leaf spot", "1500 g", "500", 30),
        {"dose_per_litre": 3.0, "dose_unit": "g", "water_l_per_acre": 200}),
    ("soybean_downy_mildew", "metalaxyl_mancozeb_72wp"): ("drop", "Metalaxyl 8% + Mancozeb 64% WP is not registered on soybean."),
    ("soybean_bacterial_blight", "copper_oxychloride_50wp"): ("drop", "Copper oxychloride 50% WP is not registered on soybean."),
}


def fetch() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for local, remote in LISTS.values():
        subprocess.run(["curl", "-sfL", "--max-time", "120", "-A", "Mozilla/5.0", "-o", str(RAW / local),
                        "https://ppqs.gov.in/sites/default/files/" + remote], check=True, timeout=180)


def main() -> None:
    if "--fetch" in sys.argv:
        fetch()
    adv = json.loads((KB / "advisories.json").read_text())
    pest = json.loads((KB / "pesticides.json").read_text())
    for pid, entry in NEW_PESTICIDES.items():
        pest.setdefault(pid, entry)

    # Timing sentences other rungs borrow, read before anything changes.
    timings = {(t, r["ingredient"]): r.get("timing") for t, a in adv.items() if not t.startswith("_")
               for r in a.get("ladder", []) if r.get("tier") == "chemical"}
    seen, counts = set(), {"verified": 0, "swapped": 0, "dropped": 0}
    for t, a in adv.items():
        if t.startswith("_"):
            continue
        ladder = []
        for r in a["ladder"]:
            if r.get("tier") != "chemical":
                ladder.append(r)
                continue
            key = (t, r["ingredient"])
            if key not in D:
                if r.get("verified") and r.get("registration"):
                    ladder.append(r)   # already checked on an earlier run
                    continue
                raise SystemExit(f"no decision for {key}")
            seen.add(key)
            d = D[key]
            if d[0] == "drop":
                counts["dropped"] += 1
                continue
            if d[0] == "swap":
                _, new, registration, changes = d
                r = {**r, "ingredient": new}
                counts["swapped"] += 1
            else:
                _, registration, changes = d
            changes = dict(changes)
            borrow = changes.pop("timing_from", None)
            if borrow:
                r["timing"] = timings[borrow]
            for k, v in changes.items():
                if v is None:
                    r.pop(k, None)
                else:
                    r[k] = v
            r["verified"] = True
            r["registration"] = registration
            counts["verified"] += 1
            ladder.append(r)
        a["ladder"] = ladder
    missing = set(D) - seen
    if missing and not all(adv.get(t) for t, _ in missing):
        raise SystemExit(f"decisions for rungs that no longer exist: {sorted(missing)}")
    adv["_note"] = adv["_note"].split(" 'verified' flips")[0].rstrip('; ') + '.' + (
        " Every chemical rung is checked against the CIB&RC Major Uses of Pesticides lists "
        "(data/verify_doses.py): 'registration' records the row it rests on — crop, pest, formulation "
        "per hectare, water per hectare, waiting period — and a rung whose product is not registered for "
        "that crop and pest is not here. Doses are per litre of water at the registered water volume; the "
        "printed label stays the authority on dose.")
    (KB / "advisories.json").write_text(json.dumps(adv, indent=1, ensure_ascii=False) + "\n")
    # pesticides.json keeps one product to a line, as it is written by hand.
    (KB / "pesticides.json").write_text(
        "{\n" + ",\n".join(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in pest.items()) + "\n}\n")
    print(counts)


if __name__ == "__main__":
    main()
