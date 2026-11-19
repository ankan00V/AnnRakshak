"""Organic steps for the problems whose advisories had too few: sourced field
practices and natural control, written into the advisories' ladders.

Every disease and pest the app advises on has to give the farmer an organic
route as well as a chemical one. Where the advice was one field step and
nothing else (false smut was one: gather the smut balls and bury them), these
add what the government IPM packages and IRRI recommend for that problem —
seed treatments, named resistant varieties, water and nitrogen management,
natural enemies, trap crops. Nothing is added that a source does not name for
that problem, and each step carries its source.

  NCIPM & DPPQS, Integrated Pest Management Packages for Rice, Maize and Soybean
      (niphm.gov.in/IPMPackages/; raw copies in data/raw/ipm/): resistant and
      tolerant varieties by disease, seed treatment with Trichoderma or
      Pseudomonas for seed-borne disease, Trichoderma harzianum seed treatment
      for banded leaf and sheath blight, dhaincha as a trap crop for girdle
      beetle, conservation of natural enemies.
  IRRI Rice Knowledge Bank, False smut: alternate wetting and drying, moderate
      nitrogen, field sanitation, hot-water seed treatment at 52 °C for 10 min.

Re-runnable: the steps it added before are taken out and written again.

    .venv/bin/python data/organic_practices.py   -> backend/kb/advisories.json
"""

from __future__ import annotations

import json
from pathlib import Path

KB = Path(__file__).resolve().parents[1] / "backend" / "kb"
TAG = "organic_practices"

RICE = "NCIPM & DPPQS, Integrated Pest Management Package for Rice"
MAIZE = "NCIPM & DPPQS, Integrated Pest Management Package for Maize"
SOY = "NCIPM & DPPQS, Integrated Pest Management Package for Soybean"
IRRI = "IRRI Rice Knowledge Bank, False smut"

STEPS: dict[str, list[tuple[str, dict, str]]] = {
    "rice_false_smut": [
        ("cultural", {
            "en": "Alternate wetting and drying instead of keeping the field flooded, keep nitrogen moderate, and after harvest clear the infected panicles and stubble from the field.",
            "hi": "खेत में लगातार पानी भरा रखने के बजाय बारी-बारी से गीला-सूखा करें, नाइट्रोजन सीमित रखें, और कटाई के बाद संक्रमित बालियाँ और ठूँठ खेत से हटा दें।",
            "mr": "शेतात सतत पाणी साचवण्याऐवजी आलटून-पालटून ओले-कोरडे करा, नत्र मर्यादित ठेवा, आणि कापणीनंतर बाधित लोंब्या व खुंट शेतातून काढून टाका.",
        }, IRRI),
        ("biological", {
            "en": "Next season, soak the seed in hot water at 52 °C for 10 minutes, or coat it with Pseudomonas fluorescens at 10 g per kg of seed.",
            "hi": "अगले मौसम में बीज को 52 °C गर्म पानी में 10 मिनट भिगोएँ, या प्रति किलो बीज 10 ग्राम स्यूडोमोनास फ्लोरेसेंस से उपचारित करें।",
            "mr": "पुढील हंगामात बियाणे 52 °C गरम पाण्यात 10 मिनिटे भिजवा, किंवा प्रति किलो बियाण्यास 10 ग्रॅम स्युडोमोनास फ्लुरोसन्स लावा.",
        }, f"{IRRI}; {RICE} (seed treatment for seed-borne disease)"),
    ],
    "rice_tungro": [
        ("cultural", {
            "en": "Tolerant varieties named in the national IPM package: Vikramarya, Nidhi, Amulya, Dinesh, Lakshmi and Nalini. Transplant seedlings older than 3 weeks, at the same time as your neighbours.",
            "hi": "राष्ट्रीय IPM पैकेज में बताई गई सहनशील किस्में: विक्रमार्य, निधि, अमूल्य, दिनेश, लक्ष्मी और नलिनी। 3 सप्ताह से पुरानी पौध रोपें, पड़ोसियों के साथ एक ही समय पर।",
            "mr": "राष्ट्रीय IPM पॅकेजमधील सहनशील वाण: विक्रमार्य, निधी, अमूल्य, दिनेश, लक्ष्मी आणि नलिनी. 3 आठवड्यांपेक्षा जुनी रोपे लावा, शेजाऱ्यांसोबत एकाच वेळी.",
        }, RICE),
        ("biological", {
            "en": "Protect the spiders, mirid bugs and other predators that eat the green leafhopper which spreads tungro: no broad-spectrum sprays early in the season.",
            "hi": "टुंग्रो फैलाने वाले हरे फुदके को खाने वाली मकड़ियों, मिरिड बग और दूसरे शिकारी कीटों को बचाएँ: मौसम की शुरुआत में व्यापक असर वाले छिड़काव न करें।",
            "mr": "टुंग्रो पसरवणाऱ्या हिरव्या तुडतुड्याला खाणारे कोळी, मिरिड ढेकूण आणि इतर भक्षक वाचवा: हंगामाच्या सुरुवातीला सर्वव्यापी फवारण्या करू नका.",
        }, RICE),
    ],
    "maize_common_rust": [
        ("cultural", {
            "en": "Resistant hybrids named in the national IPM package: Buland, Sheetal, HHM 1, HHM 2, HQPM 1 and Nithyashree.",
            "hi": "राष्ट्रीय IPM पैकेज में बताए गए प्रतिरोधी संकर: बुलंद, शीतल, HHM 1, HHM 2, HQPM 1 और नित्यश्री।",
            "mr": "राष्ट्रीय IPM पॅकेजमधील प्रतिकारक संकरित वाण: बुलंद, शीतल, HHM 1, HHM 2, HQPM 1 आणि नित्यश्री.",
        }, MAIZE),
    ],
    "maize_maydis_leaf_blight": [
        ("cultural", {
            "en": "Resistant varieties named in the national IPM package: HM 10, PAU 352, Malviya Hybrid Makka 2, PEMH 1, PEMH 5, HQPM 1, HQPM 4, HQPM 5, HQPM 7, Shaktiman 3, Shaktiman 4 and HSC 1.",
            "hi": "राष्ट्रीय IPM पैकेज में बताई गई प्रतिरोधी किस्में: HM 10, PAU 352, मालवीय हाइब्रिड मक्का 2, PEMH 1, PEMH 5, HQPM 1, HQPM 4, HQPM 5, HQPM 7, शक्तिमान 3, शक्तिमान 4 और HSC 1।",
            "mr": "राष्ट्रीय IPM पॅकेजमधील प्रतिकारक वाण: HM 10, PAU 352, मालवीय हायब्रिड मका 2, PEMH 1, PEMH 5, HQPM 1, HQPM 4, HQPM 5, HQPM 7, शक्तिमान 3, शक्तिमान 4 आणि HSC 1.",
        }, MAIZE),
    ],
    "maize_downy_mildew": [
        ("cultural", {
            "en": "Sow before the rains set in, and do not sow maize next to sorghum or after it. Resistant varieties in the national IPM package: PEMH 5, Bio 9636, DMH 1, COH(M) 4, COH(M) 5 and Nithyashree.",
            "hi": "बारिश शुरू होने से पहले बुवाई करें, और मक्का को ज्वार के पास या ज्वार के बाद न बोएँ। राष्ट्रीय IPM पैकेज की प्रतिरोधी किस्में: PEMH 5, बायो 9636, DMH 1, COH(M) 4, COH(M) 5 और नित्यश्री।",
            "mr": "पाऊस सुरू होण्यापूर्वी पेरणी करा, आणि मका ज्वारीच्या शेजारी किंवा ज्वारीनंतर पेरू नका. राष्ट्रीय IPM पॅकेजमधील प्रतिकारक वाण: PEMH 5, बायो 9636, DMH 1, COH(M) 4, COH(M) 5 आणि नित्यश्री.",
        }, MAIZE),
    ],
    "maize_banded_leaf_sheath_blight": [
        ("cultural", {
            "en": "Resistant varieties named in the national IPM package: Pratap Kanchan 2, Pratap Makka 3, Pratap Makka 5, Shaktiman 1 and Shaktiman 3.",
            "hi": "राष्ट्रीय IPM पैकेज में बताई गई प्रतिरोधी किस्में: प्रताप कंचन 2, प्रताप मक्का 3, प्रताप मक्का 5, शक्तिमान 1 और शक्तिमान 3।",
            "mr": "राष्ट्रीय IPM पॅकेजमधील प्रतिकारक वाण: प्रताप कांचन 2, प्रताप मका 3, प्रताप मका 5, शक्तिमान 1 आणि शक्तिमान 3.",
        }, MAIZE),
        ("biological", {
            "en": "Next season, coat the seed with Trichoderma harzianum 2% WP at 20 g per kg of seed.",
            "hi": "अगले मौसम में प्रति किलो बीज 20 ग्राम ट्राइकोडर्मा हार्जियानम 2% WP से बीज उपचार करें।",
            "mr": "पुढील हंगामात प्रति किलो बियाण्यास 20 ग्रॅम ट्रायकोडर्मा हर्जियानम 2% WP लावा.",
        }, MAIZE),
    ],
    "maize_turcicum_leaf_blight": [
        ("cultural", {
            "en": "Resistant varieties named in the national IPM package: PEMH 5, Vivek 21, Vivek 23, Vivek 25 and Pratap Kanchan 2; Nithyashree for Karnataka and Andhra Pradesh.",
            "hi": "राष्ट्रीय IPM पैकेज में बताई गई प्रतिरोधी किस्में: PEMH 5, विवेक 21, विवेक 23, विवेक 25 और प्रताप कंचन 2; कर्नाटक और आंध्र प्रदेश के लिए नित्यश्री।",
            "mr": "राष्ट्रीय IPM पॅकेजमधील प्रतिकारक वाण: PEMH 5, विवेक 21, विवेक 23, विवेक 25 आणि प्रताप कांचन 2; कर्नाटक व आंध्र प्रदेशासाठी नित्यश्री.",
        }, MAIZE),
    ],
    "maize_curvularia_leaf_spot": [
        ("cultural", {
            "en": "Before sowing, plough deep two or three times, 10 to 15 days apart, to bury the old crop debris and weeds; sow certified seed and throw out light, chaffy or damaged seed.",
            "hi": "बुवाई से पहले 10 से 15 दिन के अंतर पर दो-तीन बार गहरी जुताई करें, ताकि पुरानी फसल के अवशेष और खरपतवार दब जाएँ; प्रमाणित बीज बोएँ और हल्के, खोखले या टूटे बीज निकाल दें।",
            "mr": "पेरणीपूर्वी 10 ते 15 दिवसांच्या अंतराने दोन-तीन वेळा खोल नांगरट करा, म्हणजे जुन्या पिकाचे अवशेष व तण गाडले जातील; प्रमाणित बियाणे पेरा आणि हलके, पोचट किंवा तुटलेले बी काढून टाका.",
        }, f"{MAIZE} (cultural practices for diseases)"),
    ],
    "maize_ear_rot": [
        ("cultural", {
            "en": "Do not let the crop go short of water from flowering to grain filling, and do not give high nitrogen with too little potash.",
            "hi": "फूल आने से दाना भरने तक फसल में पानी की कमी न होने दें, और कम पोटाश के साथ ज़्यादा नाइट्रोजन न दें।",
            "mr": "फुलोऱ्यापासून दाणे भरेपर्यंत पिकाला पाण्याचा ताण पडू देऊ नका, आणि कमी पालाशसोबत जास्त नत्र देऊ नका.",
        }, f"{MAIZE} (cultural practices for diseases)"),
    ],
    "soybean_girdle_beetle": [
        ("cultural", {
            "en": "Grow dhaincha as a trap crop around the field: the beetles gather on it, away from the soybean.",
            "hi": "खेत के चारों ओर ढैंचा को फँसाऊ फसल के रूप में उगाएँ: भृंग सोयाबीन से हटकर उस पर जमा होते हैं।",
            "mr": "शेताभोवती धैंचा सापळा पीक म्हणून लावा: भुंगे सोयाबीनपासून दूर त्यावर जमतात.",
        }, SOY),
    ],
}


def main() -> None:
    adv = json.loads((KB / "advisories.json").read_text())
    added = 0
    for tid, entry in adv.items():
        if tid.startswith("_"):
            continue
        entry["ladder"] = [r for r in entry["ladder"] if r.get("added_by") != TAG]
    for tid, steps in STEPS.items():
        ladder = adv[tid]["ladder"]
        for tier, action, source in steps:
            rung = {"tier": tier, "action": action, "source": source, "added_by": TAG}
            # keep the ladder in order: after the last rung of the same or an earlier tier
            rank = {"cultural": 0, "biological": 1, "chemical": 2}
            at = max((i + 1 for i, r in enumerate(ladder) if rank[r["tier"]] <= rank[tier]), default=0)
            ladder.insert(at, rung)
            added += 1
    (KB / "advisories.json").write_text(json.dumps(adv, indent=1, ensure_ascii=False) + "\n")
    print(f"{added} organic steps on {len(STEPS)} problems")


if __name__ == "__main__":
    main()
