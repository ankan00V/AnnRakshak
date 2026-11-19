"""Neem preparations a farmer makes at home, where a government IPM source
recommends one for the problem — written into the advisories as `homemade`,
beside the registered organic products (data/organic_options.py).

They are not registered products: no label, no CIB&RC row, no waiting period.
So each one stands on a government source that names the preparation, the
strength and the pest, and nothing is offered on general neem lore:

  ICAR-IIMR, "Identification and management of fall armyworm" (Vikaspedia):
      5% NSKE while the young larvae scrape the leaf surface.
  APEDA Farmer Connect, IPM with recommended pesticides (Government of India):
      cotton aphid, jassid, thrips and whiteflies — NSKE 5%; leaf curl virus —
      control the whiteflies.
  NCIPM & DPPQS, IPM Package for Soybean (NIPHM): NSKE 5% for early-stage
      larvae and sucking pests; raw neem oil 1% at 30, 45 and 60 days after
      sowing for rust.
  DPPQS advisory on brown planthopper in rice (ppqs.gov.in): neem oil 5 ml with
      2 ml liquid detergent per litre at the base of the plants; NSKE 5% while
      the count is below the threshold.

The recipe for NSKE is TNAU's (Vikaspedia): 5 kg of kernels to 100 litres,
which is 500 g to a 10-litre tank.

Left out on purpose: the cow-urine, cow-milk and asafoetida sprays in the
soybean package. They are in a government document, but nothing in it or
behind it measures what they do, and the app does not advise what it cannot
stand behind.

    .venv/bin/python data/homemade_options.py   -> backend/kb/homemade.json, backend/kb/advisories.json
"""

from __future__ import annotations

import json
from pathlib import Path

KB = Path(__file__).resolve().parents[1] / "backend" / "kb"

IIMR = "ICAR-IIMR, Identification and management of fall armyworm"
APEDA = "APEDA Farmer Connect: IPM with recommended pesticides (Government of India)"
SOY = "NCIPM & DPPQS, Integrated Pest Management Package for Soybean"
BPH = "DPPQS advisory on brown planthopper in rice"

PREPARATIONS = {
    "nske_5": {
        "name": {"en": "Neem seed kernel extract (NSKE) 5%",
                 "hi": "नीम बीज गिरी अर्क (NSKE) 5%",
                 "mr": "निंबोळी अर्क (NSKE) 5%"},
        "recipe": {
            "en": [
                "For one 10-litre tank: 500 g of dry neem seed kernels, from seeds less than 8 months old.",
                "Pound them to a coarse powder and soak overnight in 1 litre of water.",
                "In the morning stir until the water turns milky, then filter through a double layer of cloth.",
                "Make it up to 10 litres. Mix 20 g of detergent into a paste and stir it in, so the spray sticks.",
                "Use it the same day, and spray after 3:30 in the afternoon.",
            ],
            "hi": [
                "10 लीटर की एक टंकी के लिए: 500 ग्राम सूखी नीम की गिरी, 8 महीने से कम पुराने बीजों से।",
                "इन्हें दरदरा कूटकर रात भर 1 लीटर पानी में भिगो दें।",
                "सुबह पानी दूधिया होने तक हिलाएँ, फिर कपड़े की दोहरी परत से छान लें।",
                "इसे 10 लीटर कर लें। 20 ग्राम डिटर्जेंट का पेस्ट बनाकर मिलाएँ, ताकि घोल पत्तों पर चिपके।",
                "इसे उसी दिन इस्तेमाल करें, और दोपहर 3:30 के बाद छिड़कें।",
            ],
            "mr": [
                "10 लिटरच्या एका टाकीसाठी: 500 ग्रॅम वाळलेल्या निंबोळ्यांचे गर, 8 महिन्यांपेक्षा कमी जुन्या बियांचे.",
                "ते जाडसर कुटून रात्रभर 1 लिटर पाण्यात भिजवा.",
                "सकाळी पाणी दुधाळ होईपर्यंत ढवळा, मग कापडाच्या दुहेरी थरातून गाळा.",
                "ते 10 लिटर करा. 20 ग्रॅम डिटर्जंटची पेस्ट करून मिसळा, म्हणजे फवारा पानांवर चिकटेल.",
                "ते त्याच दिवशी वापरा, आणि दुपारी 3:30 नंतर फवारा.",
            ],
        },
        "recipe_source": "TNAU Agritech, Neem seed kernel extract (Vikaspedia)",
    },
    "neem_oil": {
        "name": {"en": "Neem oil spray", "hi": "नीम तेल का छिड़काव", "mr": "निंबोळी तेलाची फवारणी"},
        "recipe": {
            "en": [
                "Mix the neem oil with the liquid detergent first, then add it to the water and stir well.",
                "Shake the tank as you spray: the oil floats if it is left to stand.",
                "Use it the same day.",
            ],
            "hi": [
                "पहले नीम तेल को तरल डिटर्जेंट में मिलाएँ, फिर पानी में डालकर अच्छी तरह हिलाएँ।",
                "छिड़कते समय टंकी हिलाते रहें: रखा रहने पर तेल ऊपर तैरने लगता है।",
                "इसे उसी दिन इस्तेमाल करें।",
            ],
            "mr": [
                "आधी निंबोळी तेल द्रव डिटर्जंटमध्ये मिसळा, मग पाण्यात घालून चांगले ढवळा.",
                "फवारताना टाकी हलवत राहा: ठेवून दिल्यास तेल वर तरंगते.",
                "ते त्याच दिवशी वापरा.",
            ],
        },
        "recipe_source": "DPPQS advisory on brown planthopper in rice",
    },
}


def nske(timing: dict, source: str) -> dict:
    return {"prep": "nske_5", "per_litre": {"amount": 50, "unit": "g"}, "timing": timing, "source": source}


def neem_oil(ml: float, timing: dict, source: str) -> dict:
    return {"prep": "neem_oil", "per_litre": {"amount": ml, "unit": "ml"}, "detergent_ml_per_litre": 2,
            "timing": timing, "source": source}


SUCKING = {
    "en": "Spray when you first see the insects under the leaves, covering the undersides.",
    "hi": "पत्तों के नीचे कीट दिखते ही छिड़कें, पत्तों की निचली सतह पर अच्छी तरह।",
    "mr": "पानांच्या खाली किडे दिसताच फवारा, पानांच्या खालच्या बाजूला नीट.",
}
VECTOR = {
    "en": "It keeps down the whitefly that spreads the virus; it does not cure plants already infected.",
    "hi": "यह वायरस फैलाने वाली सफेद मक्खी को कम करता है; पहले से संक्रमित पौधों को ठीक नहीं करता।",
    "mr": "हे विषाणू पसरवणाऱ्या पांढऱ्या माशीला कमी करते; आधीच बाधित झाडे बरी करत नाही.",
}

HOMEMADE = {
    "maize_fall_armyworm": [nske({
        "en": "Spray into the whorl while the young larvae are still scraping windows in the leaves, from the seedling to the early whorl stage.",
        "hi": "जब छोटी इल्लियाँ पत्तों को खुरचकर खिड़की जैसे निशान बना रही हों, तब पौध से शुरुआती गोभ अवस्था तक गोभ में छिड़कें।",
        "mr": "लहान अळ्या पानांवर खरवडून खिडकीसारख्या खुणा करत असताना, रोपावस्थेपासून सुरुवातीच्या पोंगा अवस्थेपर्यंत पोंग्यात फवारा.",
    }, IIMR)],
    "cotton_whitefly": [nske(SUCKING, APEDA)],
    "cotton_aphid": [nske(SUCKING, APEDA)],
    "cotton_jassid": [nske(SUCKING, APEDA)],
    "cotton_leaf_curl": [nske(VECTOR, APEDA)],
    "soybean_tobacco_caterpillar": [nske({
        "en": "Spray while the caterpillars are small, when you first see leaves eaten from the underside.",
        "hi": "इल्लियाँ छोटी हों तभी छिड़कें, जब पत्ते नीचे से खाए हुए पहली बार दिखें।",
        "mr": "अळ्या लहान असतानाच फवारा, पाने खालून खाल्लेली पहिल्यांदा दिसताच.",
    }, SOY)],
    "soybean_yellow_mosaic": [nske(VECTOR, SOY)],
    "soybean_rust": [neem_oil(10, {
        "en": "Three sprays: 30, 45 and 60 days after sowing.",
        "hi": "तीन छिड़काव: बुवाई के 30, 45 और 60 दिन बाद।",
        "mr": "तीन फवारण्या: पेरणीनंतर 30, 45 आणि 60 दिवसांनी.",
    }, SOY)],
    "rice_brown_planthopper": [
        neem_oil(5, {
            "en": "Spray the base of the plants, where the hoppers sit. It cuts egg-laying rather than killing outright.",
            "hi": "पौधों के निचले हिस्से पर छिड़कें, जहाँ फुदके बैठते हैं। यह मारने से ज़्यादा अंडे देना कम करता है।",
            "mr": "चुडांच्या बुडख्यावर फवारा, जिथे तुडतुडे बसतात. हे मारण्यापेक्षा अंडी घालणे कमी करते.",
        }, BPH),
        nske({
            "en": "While the count is still below about 10 hoppers per hill; aim at the base of the plants.",
            "hi": "जब तक गिनती प्रति पौधा लगभग 10 फुदकों से कम हो; पौधों के निचले हिस्से पर छिड़कें।",
            "mr": "मोजणी प्रति चूड सुमारे 10 तुडतुड्यांपेक्षा कमी असेपर्यंत; चुडांच्या बुडख्यावर फवारा.",
        }, BPH),
    ],
}


def main() -> None:
    (KB / "homemade.json").write_text(json.dumps(PREPARATIONS, indent=1, ensure_ascii=False) + "\n")
    adv = json.loads((KB / "advisories.json").read_text())
    for tid, entry in adv.items():
        if not tid.startswith("_"):
            entry.pop("homemade", None)
    for tid, items in HOMEMADE.items():
        adv[tid]["homemade"] = items
    (KB / "advisories.json").write_text(json.dumps(adv, indent=1, ensure_ascii=False) + "\n")
    print(f"{sum(len(v) for v in HOMEMADE.values())} homemade options on {len(HOMEMADE)} targets")


if __name__ == "__main__":
    main()
