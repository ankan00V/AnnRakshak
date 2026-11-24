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

PAU Ludhiana, Package of Practices for Crops of Punjab, Kharif 2026 (raw copy in
data/raw/organic/pp_kharif.pdf): PAU homemade neem extract — 4 kg of neem shoot
tips boiled in 10 litres of water — at 4 litres in 100 litres per acre for rice
planthoppers, and 1200 ml per acre for cotton whitefly.

Natural farming. ICAR, "Generic Protocols for Natural Farming", published on the
Government's natural farming portal (naturalfarming.dac.gov.in; raw copy in
data/raw/organic/), sections 8 and 9: Agniastra (leaf roller, stem borer, fruit
and pod borer), Brahmastra (sucking pests, fruit and pod borer), Neemastra
(sucking pests and leaf-eating caterpillars), Dashparni ark (borers and
caterpillars), Sonthastra and sour buttermilk (fungal diseases). Each goes only
to the pests or diseases the protocol itself names for it — sucking pests,
stem borers, caterpillars, fungal leaf diseases — and never to a virus, a
bacterium, a soil-borne wilt or a cob rot. NITI Aayog's training manual for the
National Mission on Natural Farming (2026) prints the same four pest recipes and
cites this protocol; where the two differ in amounts, the ICAR protocol is used.
The manual's other farmer formulations (its section 6.2.8) are left out: it
says itself that none has been scientifically validated.

Every preparation says who stands behind it (`backing`): "recommended" for an
ICAR, university or government IPM recommendation, "natural_farming" for the
natural farming protocol. A natural-farming preparation is not a registered
pesticide and has no tested dose for any one pest; the app shows it as what it
is, under that label, and never in place of a registered product.

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
PAU = "PAU Ludhiana, Package of Practices for Crops of Punjab, Kharif 2026"
NF = "ICAR, Generic Protocols for Natural Farming (natural farming portal, Ministry of Agriculture & Farmers Welfare)"

PER_ACRE_6_8 = {"en": "6 to 8 litres in 200 litres of water, for one acre.",
                "hi": "एक एकड़ के लिए 200 लीटर पानी में 6 से 8 लीटर।",
                "mr": "एका एकरासाठी 200 लिटर पाण्यात 6 ते 8 लिटर."}
POISON = {"en": "{what} poisonous: wear gloves, keep it away from children and animals, and wash your hands after.",
          "hi": "{what} ज़हरीला है: दस्ताने पहनें, बच्चों और पशुओं से दूर रखें, और बाद में हाथ धो लें।",
          "mr": "{what} विषारी आहे: हातमोजे घाला, मुले आणि जनावरांपासून दूर ठेवा, आणि नंतर हात धुवा."}

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
    "pau_neem_extract": {
        "name": {"en": "PAU homemade neem extract", "hi": "पीएयू घरेलू नीम अर्क", "mr": "पीएयू घरगुती कडुनिंब अर्क"},
        "recipe": {
            "en": ["Take 4 kg of the tips of neem shoots: leaves, green twigs and fruits.",
                   "Boil them in 10 litres of water for 30 minutes.",
                   "Filter through a muslin cloth and use the liquid at the dose given."],
            "hi": ["नीम की टहनियों के 4 किलो सिरे लें: पत्तियाँ, हरी टहनियाँ और फल।",
                   "इन्हें 10 लीटर पानी में 30 मिनट उबालें।",
                   "मलमल के कपड़े से छान लें और बताई गई मात्रा में इस्तेमाल करें।"],
            "mr": ["कडुनिंबाच्या फांद्यांची 4 किलो टोके घ्या: पाने, हिरव्या फांद्या आणि फळे.",
                   "ती 10 लिटर पाण्यात 30 मिनिटे उकळा.",
                   "मलमलच्या कापडाने गाळून घ्या आणि दिलेल्या प्रमाणात वापरा."],
        },
        "recipe_source": f"{PAU} (cotton chapter)",
    },
    "agniastra": {
        "name": {"en": "Agniastra", "hi": "अग्निअस्त्र", "mr": "अग्निअस्त्र"},
        "recipe": {
            "en": ["In a pot, take 20 litres of desi cow urine.",
                   "Add 500 g of crushed tobacco, 500 g of green chilli, 250 g of garlic and 5 kg of crushed neem leaves. Stir well.",
                   "Boil it, let it cool, and leave it to ferment for 48 hours.",
                   "Filter through a cloth. Use it within 3 months.",
                   POISON["en"].format(what="Tobacco is")],
            "hi": ["एक बर्तन में 20 लीटर देसी गाय का मूत्र लें।",
                   "इसमें 500 ग्राम कुचला हुआ तंबाकू, 500 ग्राम हरी मिर्च, 250 ग्राम लहसुन और 5 किलो कुटी हुई नीम की पत्तियाँ डालें। अच्छी तरह हिलाएँ।",
                   "इसे उबालें, ठंडा होने दें, और 48 घंटे किण्वन के लिए रख दें।",
                   "कपड़े से छान लें। 3 महीने के अंदर इस्तेमाल करें।",
                   POISON["hi"].format(what="तंबाकू")],
            "mr": ["एका भांड्यात 20 लिटर देशी गाईचे गोमूत्र घ्या.",
                   "त्यात 500 ग्रॅम ठेचलेली तंबाखू, 500 ग्रॅम हिरवी मिरची, 250 ग्रॅम लसूण आणि 5 किलो ठेचलेली कडुनिंबाची पाने घाला. चांगले ढवळा.",
                   "ते उकळा, थंड होऊ द्या, आणि 48 तास आंबवण्यासाठी ठेवा.",
                   "कापडाने गाळून घ्या. 3 महिन्यांच्या आत वापरा.",
                   POISON["mr"].format(what="तंबाखू")],
        },
        "dose": PER_ACRE_6_8,
        "per_acre": {"amount": [6, 8], "unit": "L", "water_l": 200},
        "recipe_source": NF,
    },
    "brahmastra": {
        "name": {"en": "Brahmastra", "hi": "ब्रह्मास्त्र", "mr": "ब्रह्मास्त्र"},
        "recipe": {
            "en": ["Crush 2 kg each of neem, karanj, custard apple (sitaphal), castor and datura leaves into a paste.",
                   "Add the paste to 10 litres of desi cow urine and boil it until it froths.",
                   "Filter it, then leave it in the shade for 48 hours to ferment, stirring twice a day.",
                   "Use it within one month.",
                   POISON["en"].format(what="Datura is")],
            "hi": ["नीम, करंज, सीताफल, अरंडी और धतूरे की 2-2 किलो पत्तियाँ कूटकर चटनी बना लें।",
                   "इस चटनी को 10 लीटर देसी गाय के मूत्र में डालें और झाग आने तक उबालें।",
                   "छान लें, फिर दिन में दो बार हिलाते हुए 48 घंटे छाया में किण्वन के लिए रखें।",
                   "एक महीने के अंदर इस्तेमाल करें।",
                   POISON["hi"].format(what="धतूरा")],
            "mr": ["कडुनिंब, करंज, सीताफळ, एरंड आणि धोत्र्याची प्रत्येकी 2 किलो पाने ठेचून चटणी करा.",
                   "ही चटणी 10 लिटर देशी गाईच्या गोमूत्रात घाला आणि फेस येईपर्यंत उकळा.",
                   "गाळून घ्या, मग दिवसातून दोनदा ढवळत 48 तास सावलीत आंबवण्यासाठी ठेवा.",
                   "एका महिन्याच्या आत वापरा.",
                   POISON["mr"].format(what="धोतरा")],
        },
        "dose": PER_ACRE_6_8,
        "per_acre": {"amount": [6, 8], "unit": "L", "water_l": 200},
        "recipe_source": NF,
    },
    "neemastra": {
        "name": {"en": "Neemastra", "hi": "नीमास्त्र", "mr": "निमास्त्र"},
        "recipe": {
            "en": ["Crush 5 kg of neem leaves into a paste.",
                   "In 100 litres of water, mix the paste with 5 litres of desi cow urine and 1 kg of fresh cow dung.",
                   "Leave it to ferment for 2 to 4 days, stirring twice a day.",
                   "Filter through a cloth."],
            "hi": ["5 किलो नीम की पत्तियाँ कूटकर चटनी बना लें।",
                   "100 लीटर पानी में यह चटनी, 5 लीटर देसी गाय का मूत्र और 1 किलो ताज़ा गोबर मिलाएँ।",
                   "दिन में दो बार हिलाते हुए 2 से 4 दिन किण्वन के लिए रखें।",
                   "कपड़े से छान लें।"],
            "mr": ["5 किलो कडुनिंबाची पाने ठेचून चटणी करा.",
                   "100 लिटर पाण्यात ही चटणी, 5 लिटर देशी गाईचे गोमूत्र आणि 1 किलो ताजे शेण मिसळा.",
                   "दिवसातून दोनदा ढवळत 2 ते 4 दिवस आंबवण्यासाठी ठेवा.",
                   "कापडाने गाळून घ्या."],
        },
        "dose": {"en": "The whole 100 litres is enough for one acre: spray it as it is, without adding water.",
                 "hi": "पूरा 100 लीटर एक एकड़ के लिए काफ़ी है: इसे बिना और पानी मिलाए वैसे ही छिड़कें।",
                 "mr": "संपूर्ण 100 लिटर एका एकरासाठी पुरेसे आहे: त्यात आणखी पाणी न मिसळता तसेच फवारा."},
        "per_acre": {"amount": 100, "unit": "L"},
        "recipe_source": NF,
    },
    "dashparni_ark": {
        "name": {"en": "Dashparni ark (ten-leaf extract)", "hi": "दशपर्णी अर्क", "mr": "दशपर्णी अर्क"},
        "recipe": {
            "en": ["In 200 litres of water, mix 20 litres of desi cow urine and 2 kg of desi cow dung. Leave it for 2 hours.",
                   "Mix in 500 g of turmeric, 500 g of ginger paste and 10 g of asafoetida (hing). Keep it in the shade for 24 hours.",
                   "Stir, then mix in 200 g of dry ginger powder, 1 kg of tobacco powder, 1 kg of hot green chilli paste and 1 kg of desi garlic paste. Leave it for 24 hours.",
                   "Crush 2 kg each of the leaves of ten plants, such as neem, karanj, castor, custard apple, bael, marigold, tulsi, datura, mango and aak, and press them into the mixture.",
                   "Cover it with a gunny bag and leave it for 30 to 40 days, stirring for 2 to 3 minutes every morning and evening. Then filter.",
                   POISON["en"].format(what="Tobacco, datura and aak are").replace("keep it away", "keep them away")],
            "hi": ["200 लीटर पानी में 20 लीटर देसी गाय का मूत्र और 2 किलो देसी गोबर मिलाएँ। 2 घंटे रखें।",
                   "इसमें 500 ग्राम हल्दी, 500 ग्राम अदरक की चटनी और 10 ग्राम हींग मिलाएँ। 24 घंटे छाया में रखें।",
                   "हिलाएँ, फिर 200 ग्राम सोंठ पाउडर, 1 किलो तंबाकू पाउडर, 1 किलो तीखी हरी मिर्च की चटनी और 1 किलो देसी लहसुन की चटनी मिलाएँ। 24 घंटे रखें।",
                   "दस पौधों की 2-2 किलो पत्तियाँ, जैसे नीम, करंज, अरंडी, सीताफल, बेल, गेंदा, तुलसी, धतूरा, आम और आक, कूटकर इस मिश्रण में दबा दें।",
                   "बोरी से ढककर 30 से 40 दिन रखें, हर सुबह-शाम 2-3 मिनट हिलाते रहें। फिर छान लें।",
                   "तंबाकू, धतूरा और आक ज़हरीले हैं: दस्ताने पहनें, बच्चों और पशुओं से दूर रखें, और बाद में हाथ धो लें।"],
            "mr": ["200 लिटर पाण्यात 20 लिटर देशी गाईचे गोमूत्र आणि 2 किलो देशी शेण मिसळा. 2 तास ठेवा.",
                   "त्यात 500 ग्रॅम हळद, 500 ग्रॅम आल्याची चटणी आणि 10 ग्रॅम हिंग मिसळा. 24 तास सावलीत ठेवा.",
                   "ढवळा, मग 200 ग्रॅम सुंठ पूड, 1 किलो तंबाखू पूड, 1 किलो तिखट हिरव्या मिरचीची चटणी आणि 1 किलो देशी लसणाची चटणी मिसळा. 24 तास ठेवा.",
                   "दहा वनस्पतींची प्रत्येकी 2 किलो पाने, जसे कडुनिंब, करंज, एरंड, सीताफळ, बेल, झेंडू, तुळस, धोतरा, आंबा आणि रुई, ठेचून या मिश्रणात दाबून घाला.",
                   "पोत्याने झाकून 30 ते 40 दिवस ठेवा, रोज सकाळ-संध्याकाळ 2-3 मिनिटे ढवळत राहा. मग गाळून घ्या.",
                   "तंबाखू, धोतरा आणि रुई विषारी आहेत: हातमोजे घाला, मुले आणि जनावरांपासून दूर ठेवा, आणि नंतर हात धुवा."],
        },
        "dose": PER_ACRE_6_8,
        "per_acre": {"amount": [6, 8], "unit": "L", "water_l": 200},
        "recipe_source": NF,
    },
    "sonthastra": {
        "name": {"en": "Sonthastra (dry ginger and milk)", "hi": "सोंठास्त्र (सोंठ और दूध)", "mr": "सुंठास्त्र (सुंठ आणि दूध)"},
        "recipe": {
            "en": ["Grind 200 g of dry ginger (sonth) to a powder. Boil it in 2 litres of water until 1 litre is left, then let it cool.",
                   "Boil 5 litres of desi cow's milk once and let it cool. Take off the cream.",
                   "Strain the ginger water and the milk through a cloth."],
            "hi": ["200 ग्राम सोंठ पीसकर पाउडर बना लें। इसे 2 लीटर पानी में तब तक उबालें जब तक 1 लीटर न बचे, फिर ठंडा होने दें।",
                   "5 लीटर देसी गाय का दूध एक बार उबालकर ठंडा करें। मलाई निकाल लें।",
                   "सोंठ का पानी और दूध कपड़े से छान लें।"],
            "mr": ["200 ग्रॅम सुंठ दळून पूड करा. ती 2 लिटर पाण्यात 1 लिटर उरेपर्यंत उकळा, मग थंड होऊ द्या.",
                   "5 लिटर देशी गाईचे दूध एकदा उकळून थंड करा. साय काढून घ्या.",
                   "सुंठेचे पाणी आणि दूध कापडाने गाळून घ्या."],
        },
        "dose": {"en": "Mix it all into 200 litres of water and spray one acre.",
                 "hi": "यह सब 200 लीटर पानी में मिलाकर एक एकड़ में छिड़कें।",
                 "mr": "हे सर्व 200 लिटर पाण्यात मिसळून एक एकर फवारा."},
        "per_acre": {"batches": 1},
        "recipe_source": NF,
    },
    "khatti_lassi": {
        "name": {"en": "Sour buttermilk spray (khatti lassi)", "hi": "खट्टी लस्सी (छाछ) का छिड़काव", "mr": "आंबट ताकाची फवारणी"},
        "recipe": {
            "en": ["Take 5 litres of sour buttermilk, 3 to 5 days old.",
                   "Keep a small piece of copper dipped in it for those 3 to 5 days."],
            "hi": ["5 लीटर खट्टी छाछ लें, 3 से 5 दिन पुरानी।",
                   "इन 3 से 5 दिनों में इसमें तांबे का एक छोटा टुकड़ा डुबोकर रखें।"],
            "mr": ["5 लिटर आंबट ताक घ्या, 3 ते 5 दिवस जुने.",
                   "त्या 3 ते 5 दिवसांत त्यात तांब्याचा एक छोटा तुकडा बुडवून ठेवा."],
        },
        "dose": {"en": "Mix the 5 litres of buttermilk into 100 litres of water, stir in 50 g of turmeric powder, and spray one acre.",
                 "hi": "5 लीटर छाछ को 100 लीटर पानी में मिलाएँ, 50 ग्राम हल्दी पाउडर घोलें, और एक एकड़ में छिड़कें।",
                 "mr": "5 लिटर ताक 100 लिटर पाण्यात मिसळा, 50 ग्रॅम हळद पूड विरघळवा, आणि एक एकर फवारा."},
        "per_acre": {"amount": 5, "unit": "L", "water_l": 100},
        "recipe_source": NF,
    },
}

# Who stands behind each preparation (see the module note).
BACKING = {"nske_5": "recommended", "neem_oil": "recommended", "pau_neem_extract": "recommended",
           "agniastra": "natural_farming", "brahmastra": "natural_farming", "neemastra": "natural_farming",
           "dashparni_ark": "natural_farming", "sonthastra": "natural_farming", "khatti_lassi": "natural_farming"}
for _k, _v in PREPARATIONS.items():
    _v["backing"] = BACKING[_k]


def nske(timing: dict, source: str) -> dict:
    return {"prep": "nske_5", "per_litre": {"amount": 50, "unit": "g"}, "timing": timing, "source": source}


def neem_oil(ml: float, timing: dict, source: str) -> dict:
    return {"prep": "neem_oil", "per_litre": {"amount": ml, "unit": "ml"}, "detergent_ml_per_litre": 2,
            "timing": timing, "source": source}


def pau_neem(dose: dict, per_acre: dict, timing: dict, source: str) -> dict:
    return {"prep": "pau_neem_extract", "dose": dose, "per_acre": per_acre, "timing": timing, "source": source}


def nf(prep: str, timing: dict) -> dict:
    """A natural-farming preparation, at the protocol's own per-acre amount."""
    return {"prep": prep, "timing": timing, "source": NF}


NF_PEST = {"en": "Spray it as a preventive every 15 days to a month, as the natural farming protocol advises, before the pest builds up.",
           "hi": "प्राकृतिक खेती के प्रोटोकॉल के अनुसार, कीट बढ़ने से पहले हर 15 दिन से एक महीने में बचाव के लिए छिड़कें।",
           "mr": "नैसर्गिक शेतीच्या प्रोटोकॉलनुसार, कीड वाढण्यापूर्वी दर 15 दिवस ते एक महिन्याने प्रतिबंधासाठी फवारा."}
NF_FUNGUS = {"en": "Spray it as a preventive every 15 days to a month while the weather favours the disease, as the natural farming protocol advises.",
             "hi": "प्राकृतिक खेती के प्रोटोकॉल के अनुसार, जब तक मौसम इस रोग के अनुकूल हो, हर 15 दिन से एक महीने में बचाव के लिए छिड़कें।",
             "mr": "नैसर्गिक शेतीच्या प्रोटोकॉलनुसार, हवामान या रोगाला पोषक असेपर्यंत दर 15 दिवस ते एक महिन्याने प्रतिबंधासाठी फवारा."}

# What the protocol names each preparation for, and the targets that are that.
SUCKING_PESTS = ["cotton_aphid", "cotton_jassid", "cotton_whitefly", "rice_brown_planthopper", "maize_aphid"]
STEM_BORERS = ["rice_yellow_stem_borer", "rice_white_stem_borer", "maize_stem_borer"]
CATERPILLARS = ["maize_fall_armyworm", "soybean_tobacco_caterpillar", "rice_skipper"]
FUNGAL_LEAF = ["rice_blast", "rice_brown_spot", "rice_sheath_blight", "rice_false_smut",
               "maize_turcicum_leaf_blight", "maize_maydis_leaf_blight", "maize_common_rust",
               "maize_curvularia_leaf_spot", "maize_gray_leaf_spot", "maize_banded_leaf_sheath_blight",
               "cotton_alternaria_leaf_spot", "soybean_rust", "soybean_frogeye_leaf_spot",
               "soybean_cercospora_leaf_blight", "soybean_septoria_brown_spot", "soybean_target_spot"]
NATURAL = {
    # 8a Agniastra: leaf roller, stem borer, fruit borer, pod borer.  8d Dashparni ark: borers, caterpillars.
    **{t: ["agniastra", "dashparni_ark"] for t in STEM_BORERS},
    "rice_leaf_folder": ["agniastra", "neemastra"],
    # 8b Brahmastra: sucking pests.  8c Neemastra: sucking pests and leaf-eating caterpillars.
    **{t: ["neemastra", "brahmastra"] for t in SUCKING_PESTS},
    **{t: ["neemastra", "dashparni_ark"] for t in CATERPILLARS},
    "cotton_american_bollworm": ["dashparni_ark"],
    "cotton_pink_bollworm": ["dashparni_ark"],
    "soybean_girdle_beetle": ["dashparni_ark"],
    # 9a Sonthastra and 9b sour buttermilk: fungal diseases.
    **{t: ["sonthastra", "khatti_lassi"] for t in FUNGAL_LEAF},
}


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
    "cotton_whitefly": [
        nske(SUCKING, APEDA),
        pau_neem({"en": "1200 ml of the extract for one acre.", "hi": "एक एकड़ के लिए 1200 मिली अर्क।",
                  "mr": "एका एकरासाठी 1200 मिली अर्क."}, {"amount": 1200, "unit": "ml"}, {
            "en": "Spray when whitefly first appears early in the season, covering the undersides of the leaves.",
            "hi": "मौसम की शुरुआत में सफेद मक्खी दिखते ही छिड़कें, पत्तों की निचली सतह पर अच्छी तरह।",
            "mr": "हंगामाच्या सुरुवातीला पांढरी माशी दिसताच फवारा, पानांच्या खालच्या बाजूला नीट.",
        }, PAU),
    ],
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
        pau_neem({"en": "4 litres of the extract in 100 litres of water, for one acre.",
                  "hi": "एक एकड़ के लिए 100 लीटर पानी में 4 लीटर अर्क।",
                  "mr": "एका एकरासाठी 100 लिटर पाण्यात 4 लिटर अर्क."}, {"amount": 4, "unit": "L", "water_l": 100}, {
            "en": "Spray at the first sign of hoppers, aiming at the base of the plants with a knapsack sprayer. Repeat if needed.",
            "hi": "फुदके दिखते ही छिड़कें, नैपसैक स्प्रेयर से पौधों के निचले हिस्से की ओर। ज़रूरत हो तो दोहराएँ।",
            "mr": "तुडतुडे दिसताच फवारा, नॅपसॅक पंपाने चुडांच्या बुडख्याकडे. गरज असल्यास पुन्हा फवारा.",
        }, f"{PAU} (organic farming chapter)"),
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
        adv[tid]["homemade"] = list(items)
    for tid, preps in NATURAL.items():
        timing = NF_FUNGUS if tid in FUNGAL_LEAF else NF_PEST
        adv[tid].setdefault("homemade", []).extend(nf(p, timing) for p in preps)
    unknown = (set(HOMEMADE) | set(NATURAL)) - set(adv)
    if unknown:
        raise SystemExit(f"homemade options for targets that do not exist: {sorted(unknown)}")
    (KB / "advisories.json").write_text(json.dumps(adv, indent=1, ensure_ascii=False) + "\n")
    n = sum(len(v) for v in HOMEMADE.values()) + sum(len(v) for v in NATURAL.values())
    print(f"{n} homemade options on {len(set(HOMEMADE) | set(NATURAL))} targets")


if __name__ == "__main__":
    main()
