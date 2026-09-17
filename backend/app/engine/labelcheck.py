"""Pesticide label check — veto, never endorse.

The farmer names (or photographs) the product they are about to spray. The
answer is a table lookup against our ingredient registry and the advisories'
chemical rungs; no model is consulted. The verdict vocabulary cannot endorse:
there is no string here containing "safe", "approved" or "you can use". The
best outcome is "no objection found — follow the printed label".
"""

from __future__ import annotations

import re

from app.kb import KB, tr

VERDICTS = {
    "NO_OBJECTION_FOUND": {
        "en": "No objection found in our records for this crop and problem. Follow the printed label for dose.",
        "hi": "इस फसल और समस्या के लिए हमारे रिकॉर्ड में कोई आपत्ति नहीं मिली। मात्रा के लिए छपे लेबल का पालन करें।",
        "mr": "या पिकासाठी व समस्येसाठी आमच्या नोंदीत कोणताही आक्षेप आढळला नाही. प्रमाणासाठी छापील लेबलचे पालन करा.",
    },
    "WRONG_CLASS": {
        "en": "This is {cls}. Your problem is {problem_kind}. Do not spray it for this.",
        "hi": "यह एक {cls} है। आपकी समस्या {problem_kind} है। इसके लिए इसका छिड़काव न करें।",
        "mr": "हे {cls} आहे. तुमची समस्या {problem_kind} आहे. यासाठी याची फवारणी करू नका.",
    },
    "WRONG_CROP": {
        "en": "Our records do not list this product for {crop}. Do not use it here without an officer's advice.",
        "hi": "हमारे रिकॉर्ड में यह उत्पाद {crop} के लिए नहीं है। अधिकारी की सलाह के बिना इसका उपयोग न करें।",
        "mr": "आमच्या नोंदीत हे उत्पादन {crop} साठी नाही. अधिकाऱ्याच्या सल्ल्याशिवाय वापरू नका.",
    },
    "NOT_FOR_TARGET": {
        "en": "Our records do not list this product against {target}. It may not work and wastes money.",
        "hi": "हमारे रिकॉर्ड में यह उत्पाद {target} के विरुद्ध नहीं है। यह असर नहीं करेगा और पैसा बर्बाद होगा।",
        "mr": "आमच्या नोंदीत हे उत्पादन {target} विरुद्ध नाही. ते काम करणार नाही व पैसा वाया जाईल.",
    },
    "NOT_IN_RECORDS": {
        "en": "I do not have a record of this product. Ask an expert before using it.",
        "hi": "मेरे पास इस उत्पाद का रिकॉर्ड नहीं है। उपयोग से पहले विशेषज्ञ से पूछें।",
        "mr": "माझ्याकडे या उत्पादनाची नोंद नाही. वापरण्यापूर्वी तज्ज्ञांना विचारा.",
    },
    "HERBICIDE": {
        "en": "This is a weed killer (herbicide). It does nothing against pests or diseases and can damage your crop.",
        "hi": "यह खरपतवारनाशक है। यह कीट या रोग पर असर नहीं करता और फसल को नुकसान पहुँचा सकता है।",
        "mr": "हे तणनाशक आहे. ते कीड किंवा रोगावर काम करत नाही आणि पिकाचे नुकसान करू शकते.",
    },
    "NO_DIAGNOSIS": {
        "en": "There is no confirmed problem on this field yet, so there is nothing to spray for. Get a diagnosis first.",
        "hi": "इस खेत पर अभी कोई पुष्ट समस्या नहीं है, इसलिए छिड़काव का कारण नहीं। पहले निदान कराएँ।",
        "mr": "या शेतावर अद्याप कोणतीही निश्चित समस्या नाही, म्हणून फवारणीचे कारण नाही. आधी निदान करा.",
    },
}

CLASS_WORDS = {
    "fungicide": {"en": "a fungicide (for fungal disease)", "hi": "फफूँदनाशक", "mr": "बुरशीनाशक"},
    "insecticide": {"en": "an insecticide (for insects)", "hi": "कीटनाशक", "mr": "कीटकनाशक"},
    "herbicide": {"en": "a weed killer (herbicide)", "hi": "खरपतवारनाशक", "mr": "तणनाशक"},
}
PROBLEM_KIND = {
    "disease": {"en": "a fungal or bacterial disease", "hi": "फफूँद या जीवाणु रोग", "mr": "बुरशी किंवा जिवाणूजन्य रोग"},
    "virus": {"en": "a virus spread by insects", "hi": "कीटों से फैलने वाला वायरस", "mr": "कीटकांमुळे पसरणारा विषाणू"},
    "pest": {"en": "an insect pest", "hi": "कीट", "mr": "कीड"},
}
# Which pesticide classes can plausibly act on each problem kind. A virus has no
# chemical cure, but its insect vector does, so insecticides are not a class
# mismatch for a virus.
CLASS_FITS = {
    "disease": {"fungicide"},
    "virus": {"insecticide"},
    "pest": {"insecticide"},
}


DOSE = re.compile(r"\d+\s*(?:%|ml|l|litre|liter|g|gm|gram|kg|mg|ppm|acre|hectare|ha)\b", re.I)


def safe_suggestion(kb: KB, text: str | None) -> str | None:
    """A model's explanation of an unrecognised input, or None if it strayed.

    The model is told to explain and never to recommend. Being told is not a
    guarantee, so two things are checked in code before a farmer sees it:

      - no dose, quantity or concentration anywhere in it;
      - no pesticide name from our own list — the moment it names a chemical,
        a farmer will read it as a suggestion to buy that chemical, whatever
        the sentence around it says.

    Either way it fails closed: the farmer keeps the verified refusal and loses
    only the extra sentence.
    """
    if not text:
        return None
    if DOSE.search(text):
        return None
    low = text.lower()
    for pid, p in kb.pesticides.items():
        if pid.startswith("_"):
            continue
        for name in (p["name"], *p.get("aliases", [])):
            token = name.lower().split()[0]
            if len(token) > 4 and token in low:
                return None
    return text


def check(kb: KB, query: str, crop: str, target: str | None, lang: str) -> dict:
    ingredient = kb.match_pesticide(query)

    def verdict(code: str, **fmt) -> dict:
        text = tr(VERDICTS[code], lang).format(**fmt) if fmt else tr(VERDICTS[code], lang)
        return {
            "code": code,
            "message": text,
            "ingredient": ingredient,
            "product": kb.pesticides[ingredient]["name"] if ingredient else None,
            "is_veto": code != "NO_OBJECTION_FOUND",
            # Three different things, and a farmer should be able to tell them
            # apart at a glance. "stop" is a product we know is wrong here — a
            # herbicide on a disease, a fungicide on an insect. "unknown" is a
            # word we simply do not hold a record for, which is not the same
            # accusation: typing "water" and being told "DO NOT SPRAY THIS" in
            # red reads as if water were dangerous. Both still refuse to endorse,
            # and is_veto stays true for both so nothing downstream treats an
            # unrecognised input as approved.
            "tone": "ok" if code == "NO_OBJECTION_FOUND" else "unknown" if code == "NOT_IN_RECORDS" else "stop",
        }

    if ingredient is None:
        return verdict("NOT_IN_RECORDS")

    pest = kb.pesticides[ingredient]
    cls = pest["class"]
    crop_name = tr(kb.crops[crop]["names"], lang)

    if cls == "herbicide":
        return verdict("HERBICIDE")
    if target is None:
        return verdict("NO_DIAGNOSIS")

    kind = kb.targets[target]["kind"]
    if cls not in CLASS_FITS[kind]:
        return verdict(
            "WRONG_CLASS",
            cls=tr(CLASS_WORDS[cls], lang),
            problem_kind=tr(PROBLEM_KIND[kind], lang),
        )

    uses = kb.registered_uses(ingredient)
    if not any(c == crop for c, _ in uses):
        return verdict("WRONG_CROP", crop=crop_name)
    if (crop, target) not in uses:
        return verdict("NOT_FOR_TARGET", target=tr(kb.targets[target]["names"], lang))
    return verdict("NO_OBJECTION_FOUND")
