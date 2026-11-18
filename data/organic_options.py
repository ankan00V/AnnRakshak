"""Add the organic options to backend/kb/advisories.json: the bio-pesticides
(living fungi, bacteria and viruses) and neem products that India registers for
each crop and pest.

Source: the CIB&RC 'Major Uses of Pesticides' lists for bio-insecticides and
bio-fungicides (Registered under the Insecticides Act, 1968), as on 30.09.2026,
read into data/raw/cibrc/ by data/verify_doses.py --fetch. As with the chemical
rungs, each option was matched by hand to its row — crop, pest, formulation per
hectare, water per hectare, waiting period — and the table below is the record.
Nothing here is a use the list does not carry: a target with no registered bio
product gets no organic option, and the app says so instead of inventing one.

Doses are converted the same way as the chemical rungs: product per litre of
water at the registered water volume (litres per acre = litres per hectare ÷
2.471), rounded to an amount a farmer can measure.

    .venv/bin/python data/organic_options.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "backend" / "kb"

SOURCE = {"BI": "CIB&RC Major Uses of Pesticides — Bio-insecticides, as on 30.09.2026",
          "BF": "CIB&RC Major Uses of Pesticides — Bio-fungicides, as on 30.09.2026"}

# kind: "bio-agent" is a living organism (fungus, bacterium, virus); "botanical"
# is a plant extract. class keeps the label check's insecticide/fungicide logic.
PRODUCTS = {
    "azadirachtin_0_15ec": {"name": "Azadirachtin 0.15% EC (neem, 1500 ppm)", "class": "insecticide",
                            "organic": True, "kind": "botanical",
                            "aliases": ["azadirachtin", "neem", "neem oil", "nimbecidine", "नीम", "नीम तेल",
                                        "कडुनिंब", "निंबोळी"]},
    "azadirachtin_5": {"name": "Azadirachtin 5% (neem extract concentrate)", "class": "insecticide",
                       "organic": True, "kind": "botanical",
                       "aliases": ["azadirachtin 5", "azadirachtin 5%", "neem extract concentrate"]},
    "bt_kurstaki_wp": {"name": "Bacillus thuringiensis var. kurstaki (Bt) WP", "class": "insecticide",
                       "organic": True, "kind": "bio-agent",
                       "aliases": ["bacillus thuringiensis", "bt kurstaki", "btk"]},
    "beauveria_1_15wp": {"name": "Beauveria bassiana 1.15% WP", "class": "insecticide",
                         "organic": True, "kind": "bio-agent",
                         "aliases": ["beauveria", "beauveria bassiana", "ब्यूवेरिया", "बिव्हेरिया"]},
    "beauveria_1_5as": {"name": "Beauveria bassiana 1.5% AS (liquid)", "class": "insecticide",
                        "organic": True, "kind": "bio-agent",
                        "aliases": ["beauveria bassiana 1.5", "beauveria 1.5% as", "beauveria liquid"]},
    "metarhizium_1_15wp": {"name": "Metarhizium anisopliae 1.15% WP", "class": "insecticide",
                           "organic": True, "kind": "bio-agent",
                           "aliases": ["metarhizium", "metarhizium anisopliae", "मेटाराइजियम", "मेटारायझियम"]},
    "lecanicillium_1_15wp": {"name": "Verticillium (Lecanicillium) lecanii 1.15% WP", "class": "insecticide",
                             "organic": True, "kind": "bio-agent",
                             "aliases": ["verticillium", "verticillium lecanii", "lecanicillium", "वर्टिसिलियम",
                                         "व्हर्टिसिलियम"]},
    "hanpv_0_43as": {"name": "HaNPV 0.43% AS (virus of Helicoverpa)", "class": "insecticide",
                     "organic": True, "kind": "bio-agent",
                     "aliases": ["hanpv", "ha npv", "helicoverpa npv", "nuclear polyhedrosis virus", "एनपीवी"]},
    "trichoderma_viride_1wp": {"name": "Trichoderma viride 1% WP", "class": "fungicide",
                               "organic": True, "kind": "bio-agent",
                               "aliases": ["trichoderma", "trichoderma viride", "ट्राइकोडर्मा", "ट्रायकोडर्मा"]},
    "bacillus_subtilis_2as": {"name": "Bacillus subtilis 2% AS", "class": "fungicide",
                              "organic": True, "kind": "bio-agent",
                              "aliases": ["bacillus subtilis", "बैसिलस सबटिलिस", "बॅसिलस सबटिलिस"]},
    "pseudomonas_0_5wp": {"name": "Pseudomonas fluorescens 0.5% WP", "class": "fungicide",
                          "organic": True, "kind": "bio-agent",
                          "aliases": ["pseudomonas", "pseudomonas fluorescens", "स्यूडोमोनास", "स्युडोमोनास"]},
    "pseudomonas_1_5wp": {"name": "Pseudomonas fluorescens 1.5% WP", "class": "fungicide",
                          "organic": True, "kind": "bio-agent",
                          "aliases": ["pseudomonas fluorescens 1.5", "pseudomonas 1.5% wp"]},
}


def reg(lst, crop, pest, per_ha, water, wait=None):
    return {"source": SOURCE[lst], "crop": crop, "pest": pest, "formulation_per_ha": per_ha,
            "water_l_per_ha": water, "waiting_days": wait}


def spray(ing, dose, unit, water, timing, registration):
    return {"ingredient": ing, "use": "spray", "dose_per_litre": dose, "dose_unit": unit,
            "water_l_per_acre": water, "timing": timing, "registration": registration}


def per_acre(ing, amount, unit, timing, registration):
    return {"ingredient": ing, "use": "spray", "per_acre": {"amount": amount, "unit": unit},
            "timing": timing, "registration": registration}


def seed(ing, amount, unit, timing, registration):
    return {"ingredient": ing, "use": "seed", "per_kg_seed": {"amount": amount, "unit": unit},
            "timing": timing, "registration": registration}


def root_dip(ing, dose, unit, minutes, timing, registration):
    return {"ingredient": ing, "use": "root_dip", "dose_per_litre": dose, "dose_unit": unit,
            "minutes": minutes, "timing": timing, "registration": registration}


# When to use each one. Living products are weakened by sun and dryness; neem
# deters feeding and egg-laying more than it kills, so it is used early.
BT = {"en": "Spray in the evening when young caterpillars are seen; sunlight breaks Bt down.",
      "hi": "छोटी इल्लियाँ दिखें तो शाम को छिड़कें; धूप Bt को नष्ट कर देती है।",
      "mr": "लहान अळ्या दिसताच संध्याकाळी फवारा; उन्हाने Bt नष्ट होते."}
FUNGUS = {"en": "Spray in the evening on a moist crop; the fungus needs humidity to infect the pest.",
          "hi": "शाम को नम फसल पर छिड़कें; फफूंद को कीट को संक्रमित करने के लिए नमी चाहिए।",
          "mr": "संध्याकाळी ओलसर पिकावर फवारा; बुरशीला किडीला बाधित करण्यासाठी ओलावा लागतो."}
FUNGUS_BPH = {"en": "Spray the base of the plants in the evening; the fungus needs humidity to infect the hoppers.",
              "hi": "शाम को पौधों के निचले हिस्से पर छिड़कें; फफूंद को फुदकों को संक्रमित करने के लिए नमी चाहिए।",
              "mr": "संध्याकाळी चुडांच्या बुडख्यावर फवारा; बुरशीला तुडतुड्यांना बाधित करण्यासाठी ओलावा लागतो."}
FUNGUS_FAW = {"en": "Spray into the leaf whorl in the evening while the larvae are small.",
              "hi": "इल्लियाँ छोटी हों तब शाम को पत्तियों के गोभ में छिड़कें।",
              "mr": "अळ्या लहान असताना संध्याकाळी पोंग्यात फवारा."}
NEEM = {"en": "Spray early, when the pest first appears; neem stops feeding and egg-laying more than it kills.",
        "hi": "कीट दिखते ही जल्दी छिड़कें; नीम कीट को मारने से ज़्यादा उसका खाना और अंडे देना रोकता है।",
        "mr": "कीड दिसताच लवकर फवारा; कडुनिंब कीड मारण्यापेक्षा तिचे खाणे आणि अंडी घालणे थांबवतो."}
NEEM_PBW = {"en": "Spray from first flowering, before the larvae enter the bolls; it cannot reach larvae already inside.",
            "hi": "पहले फूल आने से छिड़कें, इल्ली के टिंडे में घुसने से पहले; अंदर घुसी इल्ली तक यह नहीं पहुँचता।",
            "mr": "पहिल्या फुलोऱ्यापासून, अळी बोंडात शिरण्यापूर्वी फवारा; आत शिरलेल्या अळीपर्यंत ते पोहोचत नाही."}
NPV = {"en": "Spray in the evening when the caterpillars are small; the virus works on young larvae.",
       "hi": "इल्लियाँ छोटी हों तब शाम को छिड़कें; विषाणु छोटी इल्लियों पर असर करता है।",
       "mr": "अळ्या लहान असताना संध्याकाळी फवारा; विषाणू लहान अळ्यांवर परिणाम करतो."}
TV_SHEATH = {"en": "Start 30 days after planting; spray three times, 15 days apart.",
             "hi": "रोपाई के 30 दिन बाद शुरू करें; 15 दिन के अंतर पर तीन बार छिड़कें।",
             "mr": "लागवडीनंतर 30 दिवसांनी सुरू करा; 15 दिवसांच्या अंतराने तीन वेळा फवारा."}
BS_SPRAY = {"en": "Spray 40–45 days after transplanting.",
            "hi": "रोपाई के 40–45 दिन बाद छिड़कें।",
            "mr": "पुनर्लागवडीनंतर 40–45 दिवसांनी फवारा."}
AT_TRANSPLANT = {"en": "At transplanting, before the seedlings go into the field.",
                 "hi": "रोपाई के समय, पौध खेत में लगाने से पहले।",
                 "mr": "पुनर्लागवडीच्या वेळी, रोपे शेतात लावण्यापूर्वी."}
FIRST_SPOTS = {"en": "Spray when the first spots appear.",
               "hi": "पहले धब्बे दिखते ही छिड़कें।",
               "mr": "पहिले ठिपके दिसताच फवारा."}
NEXT_SOWING = {"en": "For your next sowing: coat the seed evenly, dry it in shade, then sow.",
               "hi": "अगली बुवाई के लिए: बीज पर समान रूप से लगाएँ, छाया में सुखाएँ, फिर बोएँ।",
               "mr": "पुढील पेरणीसाठी: बियाण्यावर सारखे लावा, सावलीत वाळवा, मग पेरा."}

# Registrations each option rests on, by row of the CIB&RC lists.
BTK_RICE = reg("BI", "Rice (Paddy)", "Stem borer & Leaf folder", "1.50 kg", "500-750")
BTK_COTTON = reg("BI", "Cotton", "Bollworms, Spodoptera", "0.75-1.00 kg", "500-750")
BTK_SOY = reg("BI", "Soybean", "Spodoptera, Heliothis, Spilosoma, Semilooper, Leaf miner", "0.75 kg", "500-750")
AZA_RICE = reg("BI", "Rice (Paddy)", "Brown plant hopper, Leaf folder", "1500-2500 ml", "500", 5)
AZA5_RICE = reg("BI", "Rice (Paddy)", "Brown plant hopper, Leaf folder, Stem borer", "200 ml", "400", 5)
AZA_COTTON = reg("BI", "Cotton", "White fly, Bollworms", "2500-5000 ml", "500-1000", 5)
AZA5_COTTON = reg("BI", "Cotton", "Whitefly, Leaf hoppers, Helicoverpa armigera, Aphids", "375 ml", "750", 5)
VL_COTTON = reg("BI", "Cotton", "White flies", "2500 g", "500")

O = {
    "rice_blast": [
        per_acre("pseudomonas_0_5wp", 400, "g", FIRST_SPOTS,
                 reg("BF", "Rice", "Leaf and neck blast (Pyricularia oryzae)", "1 kg", None)),
        seed("pseudomonas_0_5wp", 10, "g", NEXT_SOWING,
             reg("BF", "Rice", "Leaf and neck blast (Pyricularia oryzae)", "10 g/kg seed", None)),
    ],
    "rice_brown_spot": [
        seed("pseudomonas_1_5wp", 5, "g", NEXT_SOWING,
             reg("BF", "Paddy", "Leaf spot (Helminthosporium oryzae)", "5 g/kg seed", None)),
    ],
    "rice_bacterial_leaf_blight": [
        spray("bacillus_subtilis_2as", 4, "ml", 200, BS_SPRAY,
              reg("BF", "Paddy", "Bacterial leaf blight (Xanthomonas oryzae pv. oryzae)", "1.87-2.50 litre", "500")),
        root_dip("bacillus_subtilis_2as", 10, "ml", 30, AT_TRANSPLANT,
                 reg("BF", "Paddy", "Bacterial leaf blight (Xanthomonas oryzae pv. oryzae)", "10 ml/litre of water", None)),
        seed("pseudomonas_1_5wp", 5, "g", NEXT_SOWING,
             reg("BF", "Paddy", "Bacterial leaf blight (Xanthomonas oryzae)", "5 g/kg seed", None)),
    ],
    "rice_sheath_blight": [
        spray("trichoderma_viride_1wp", 5, "g", 200, TV_SHEATH,
              reg("BF", "Paddy", "Sheath blight (Rhizoctonia solani)", "2.5 kg", "500")),
    ],
    "rice_leaf_folder": [
        spray("bt_kurstaki_wp", 3, "g", 200, BT, BTK_RICE),
        spray("beauveria_1_15wp", 3.4, "g", 300, FUNGUS,
              reg("BI", "Rice (Paddy)", "Leaf folder (Cnaphalocrocis medinalis)", "2.5 kg", "750-850")),
        spray("azadirachtin_0_15ec", 3, "ml", 200, NEEM, AZA_RICE),
    ],
    "rice_yellow_stem_borer": [
        spray("bt_kurstaki_wp", 3, "g", 200, BT, BTK_RICE),
        spray("azadirachtin_5", 0.5, "ml", 160, NEEM, AZA5_RICE),
    ],
    "rice_white_stem_borer": [
        spray("bt_kurstaki_wp", 3, "g", 200, BT, BTK_RICE),
        spray("azadirachtin_5", 0.5, "ml", 160, NEEM, AZA5_RICE),
    ],
    "rice_brown_planthopper": [
        spray("metarhizium_1_15wp", 5, "g", 200, FUNGUS_BPH,
              reg("BI", "Rice", "Brown plant hopper (Nilaparvata lugens)", "2.5 kg", "500")),
        spray("azadirachtin_0_15ec", 3, "ml", 200, NEEM, AZA_RICE),
    ],
    "maize_fall_armyworm": [
        spray("beauveria_1_5as", 6.3, "ml", 200, FUNGUS_FAW,
              reg("BI", "Maize", "Fall army worm (Spodoptera frugiperda)", "3125 ml", "500")),
    ],
    "cotton_american_bollworm": [
        spray("hanpv_0_43as", 5.4, "ml", 200, NPV,
              reg("BI", "Cotton", "Helicoverpa armigera", "2700 ml", "400-600")),
        spray("bt_kurstaki_wp", 1.5, "g", 200, BT, BTK_COTTON),
        spray("azadirachtin_0_15ec", 5, "ml", 200, NEEM, AZA_COTTON),
    ],
    "cotton_pink_bollworm": [
        spray("azadirachtin_0_15ec", 5, "ml", 200, NEEM_PBW, AZA_COTTON),
    ],
    "cotton_whitefly": [
        spray("lecanicillium_1_15wp", 5, "g", 200, FUNGUS, VL_COTTON),
        spray("azadirachtin_0_15ec", 5, "ml", 200, NEEM, AZA_COTTON),
    ],
    # Leaf curl is a virus the whitefly carries; the registrations are for the whitefly.
    "cotton_leaf_curl": [
        spray("lecanicillium_1_15wp", 5, "g", 200, FUNGUS, VL_COTTON),
        spray("azadirachtin_0_15ec", 5, "ml", 200, NEEM, AZA_COTTON),
    ],
    "cotton_jassid": [spray("azadirachtin_5", 0.5, "ml", 300, NEEM, AZA5_COTTON)],
    "cotton_aphid": [spray("azadirachtin_5", 0.5, "ml", 300, NEEM, AZA5_COTTON)],
    "cotton_bacterial_blight": [
        seed("pseudomonas_0_5wp", 10, "g", NEXT_SOWING,
             reg("BF", "Cotton", "Bacterial leaf blight", "10 g/kg seed", None)),
    ],
    "soybean_tobacco_caterpillar": [spray("bt_kurstaki_wp", 1.5, "g", 200, BT, BTK_SOY)],
}


def main() -> None:
    adv = json.loads((KB / "advisories.json").read_text())
    pest = json.loads((KB / "pesticides.json").read_text())
    for pid, entry in PRODUCTS.items():
        pest[pid] = entry
    for t, a in adv.items():
        if t.startswith("_"):
            continue
        if t in O:
            a["organic"] = O[t]
        else:
            a.pop("organic", None)
    unknown = set(O) - set(adv)
    if unknown:
        raise SystemExit(f"organic options for targets that do not exist: {sorted(unknown)}")
    note = adv["_note"].split(" 'organic' lists")[0]
    adv["_note"] = note + (
        " 'organic' lists the bio-pesticides and neem products registered for that crop and pest in the "
        "CIB&RC Major Uses lists for bio-insecticides and bio-fungicides (data/organic_options.py), each with "
        "the registration it rests on; a target with none registered has no 'organic' list.")
    (KB / "advisories.json").write_text(json.dumps(adv, indent=1, ensure_ascii=False) + "\n")
    (KB / "pesticides.json").write_text(
        "{\n" + ",\n".join(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in pest.items()) + "\n}\n")
    print(f"{sum(len(v) for v in O.values())} organic options on {len(O)} targets, {len(PRODUCTS)} products")


if __name__ == "__main__":
    main()
