"""Questions about a pest or disease — answered from the advisories, never made up.

Krishi used to explain the app and little else: "how do I control stem borer
organically", "what is blast", "can I use mancozeb on blast" all got a line
about photo diagnosis, and a Marathi question about whitefly got "I didn't
understand". The answers were in the knowledge base the whole time; nothing
read them for a question.

This reads them. Four kinds of question:

  * A named pest or disease, in any of the app's languages or in Latin letters
    ("tana chhedak", "gulabi sundi"): what it is and how to recognise it, or what
    to do — organic first, at all three levels the advice screen shows
    (registered by CIB&RC, recommended by ICAR or a university, natural-farming
    guidance), then the registered chemical, then what not to do.
  * Symptoms with no name ("brown spots with grey centres on rice"): the
    problems on that crop whose signs read like that, each with its signs, and
    a photo to tell them apart. It never names one: many look alike, and
    Krishi has always said it cannot diagnose from words (topic
    `diagnose_problem`). This lists; the photo decides.
  * A product for a problem ("can I use mancozeb on blast"): the spray check's
    own verdict, from the CIB&RC register (engine.labelcheck).
  * How to make a home or natural-farming preparation ("how to make neemastra"):
    its recipe, strength and source.

Every sentence is the knowledge base's own words in the farmer's language,
placed in a template. The language model, when there is one, only ever picks
an id from a closed list — which pest a messy question names, which of a few
candidates a description fits best — and its pick is checked against that
list. It writes nothing the farmer reads.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

from app import llm
from app.engine import advisory as advisory_engine
from app.engine import labelcheck
from app.i18n import LANGS
from app.kb import KB, tr, trl

# The crops, as farmers name them.
CROP_WORDS = {
    "rice": ["rice", "paddy", "dhan", "dhaan", "chawal", "bhat", "bhaat", "धान", "चावल", "भात", "भाताच्या", "भातावर",
             "भातावरील", "धान्य"],
    "maize": ["maize", "corn", "makka", "makai", "makka", "maka", "मक्का", "मक्के", "मका", "मक्याच्या", "मक्यावर",
              "मक्यावरील"],
    "cotton": ["cotton", "kapas", "kapaas", "narma", "kapus", "कपास", "कापूस", "कापसावर", "कापसावरील", "कापसाच्या",
               "नरमा"],
    "soybean": ["soybean", "soyabean", "soya", "soy", "सोयाबीन", "सोयाबीनवर", "सोयाबीनवरील", "सोयाबीनच्या"],
}

# Pest and disease names as farmers write them in Latin letters. Only names
# extension workers use and that cannot be confused with an everyday word;
# each maps to the targets it can mean, and the crop decides between them.
ROMAN = {
    "tana chhedak": ["rice_yellow_stem_borer", "rice_white_stem_borer", "maize_stem_borer"],
    "tana chedak": ["rice_yellow_stem_borer", "rice_white_stem_borer", "maize_stem_borer"],
    "tanachhedak": ["rice_yellow_stem_borer", "rice_white_stem_borer", "maize_stem_borer"],
    "khod kida": ["rice_yellow_stem_borer", "rice_white_stem_borer", "maize_stem_borer"],
    "khodkida": ["rice_yellow_stem_borer", "rice_white_stem_borer", "maize_stem_borer"],
    "patti lapetak": ["rice_leaf_folder"],
    "patta lapetak": ["rice_leaf_folder"],
    "bhura fudka": ["rice_brown_planthopper"],
    "bhura phudka": ["rice_brown_planthopper"],
    "safed makhi": ["cotton_whitefly"],
    "safed makkhi": ["cotton_whitefly"],
    "pandhri mashi": ["cotton_whitefly"],
    "mahu": ["cotton_aphid", "maize_aphid"],
    "maahu": ["cotton_aphid", "maize_aphid"],
    "mava": ["cotton_aphid", "maize_aphid"],
    "tudtude": ["cotton_jassid", "rice_brown_planthopper"],
    "hara tela": ["cotton_jassid"],
    "gulabi sundi": ["cotton_pink_bollworm"],
    "gulabi bondali": ["cotton_pink_bollworm"],
    "gulabi bond ali": ["cotton_pink_bollworm"],
    "lashkari ali": ["maize_fall_armyworm"],
    "lashkari aali": ["maize_fall_armyworm"],
    "sainik keet": ["maize_fall_armyworm"],
    "chakri bhrung": ["soybean_girdle_beetle"],
    "chakra bhunga": ["soybean_girdle_beetle"],
    "peela mosaic": ["soybean_yellow_mosaic"],
    "pila mosaic": ["soybean_yellow_mosaic"],
    "pivla mosaic": ["soybean_yellow_mosaic"],
    "jhonka": ["rice_blast"],
    "karpa": ["rice_blast"],
    "gerua": ["soybean_rust", "maize_common_rust"],
    "tambera": ["soybean_rust", "maize_common_rust"],
    "patti marod": ["cotton_leaf_curl"],
    "pan gundali": ["cotton_leaf_curl"],
}

# Words that are in many names and name nothing on their own: "leaf spot" is
# a dozen diseases. A match has to include at least one word not in here.
GENERIC = frozenset("""
leaf leaves spot spots blight rot disease pest insect bug worm caterpillar larva damage
virus mosaic yellow brown white green red black grey gray stem shoot root plant crop
rust mildew wilt borer bollworm hopper fly beetle mite deficiency disorder
रोग कीट कीड पत्ती पत्ते पान पाने धब्बे ठिपके झुलसा करपा अळी इल्ली सुंडी
""".split())

# What the farmer wants to know.
CUES = {
    "identify": ["what is", "what's", "identify", "recognise", "recognize", "symptom", "symptoms", "look like",
                 "kya hai", "kya hota", "kaisa dikhta", "pehchan", "pahchan", "lakshan", "kay aahe", "olakh",
                 "क्या है", "क्या होता", "पहचान", "लक्षण", "काय आहे", "ओळख", "कसा दिसतो", "कशी दिसते"],
    "organic": ["organic", "organically", "natural", "naturally", "without chemical", "without chemicals",
                "jaivik", "jaivic", "sendriya", "neem", "desi", "gharelu", "home made", "homemade", "bio",
                "जैविक", "प्राकृतिक", "सेंद्रिय", "नैसर्गिक", "देसी", "घरेलू", "नीम", "कडुनिंब", "निंबोळी"],
    "chemical": ["chemical", "pesticide", "insecticide", "fungicide", "spray", "dawai", "dawa", "dava", "aushadh",
                 "kitnashak", "rasayan", "favarni", "which medicine",
                 "रासायनिक", "रसायन", "कीटनाशक", "दवा", "दवाई", "दवाई", "फवारणी", "औषध", "कीटकनाशक", "छिड़काव"],
    "recipe": ["how to make", "how do i make", "recipe", "prepare", "kaise banaye", "kaise banate", "banane ki vidhi",
               "kase banvayche", "kashi banvaychi", "कैसे बनाएँ", "कैसे बनाए", "बनाने की विधि", "कसे बनवायचे",
               "कशी बनवायची", "तयार कसे"],
}
# A question that is asking about a product: "can I use", "kya daal sakte".
PRODUCT_CUES = ["can i use", "can i spray", "should i use", "is it safe", "safe to use", "kya daal", "kya dal",
                "daal sakte", "dal sakte", "chhidak sakte", "vapru shakto", "favaru shakto",
                "डाल सकते", "छिड़क सकते", "इस्तेमाल कर सकते", "वापरू शकतो", "फवारू शकतो"]
# Signs of a description rather than a name.
SYMPTOM_CUES = ["leaf", "leaves", "spot", "spots", "patch", "patches", "yellow", "brown", "white", "black",
                "hole", "holes", "dry", "drying", "wilting", "wilt", "curl", "curling", "stripe", "streak",
                "patta", "patte", "patti", "pila", "peela", "peele", "bhura", "bhure", "sukh", "sukh rahe", "chhed",
                "daag", "dhabba", "dhabbe", "keede", "keeda", "illi", "pane", "panavar", "thipke", "pivle", "pivli",
                "पत्ते", "पत्ती", "पत्तों", "पान", "पाने", "पानांवर", "पीला", "पीले", "पिवळी", "पिवळे", "भूरे", "भुरे",
                "धब्बे", "ठिपके", "सूख", "सुक", "छेद", "छिद्र", "डाग", "मुरड", "गुंडाळ"]

MIN_NAME = 0.6
"""A name match below this share of the name's words is not a name match."""
MIN_SYMPTOM = 0.20
"""Below this, a description matches no sign well enough to list it."""

TEXT = {
    "p_ident": {"en": "{name} ({crop}): {signature}",
                "hi": "{name} ({crop}): {signature}",
                "mr": "{name} ({crop}): {signature}"},
    "p_control": {"en": "What to do about {name} on {crop}, safest first:",
                  "hi": "{crop} में {name} के लिए क्या करें, सबसे सुरक्षित पहले:",
                  "mr": "{name} ({crop}) साठी काय करावे, सर्वात सुरक्षित आधी:"},
    "p_organic": {"en": "Organic ways to manage {name} on {crop}:",
                  "hi": "{crop} में {name} के जैविक उपाय:",
                  "mr": "{name} ({crop}) चे सेंद्रिय उपाय:"},
    "p_chemical": {"en": "The chemical for {name} on {crop}: only if it keeps spreading after the organic steps.",
                   "hi": "{crop} में {name} की रासायनिक दवा: जैविक उपायों के बाद भी फैलता रहे, तभी।",
                   "mr": "{name} ({crop}) चे रासायनिक औषध: सेंद्रिय उपायांनंतरही पसरत राहिल्यासच."},
    "s_field": {"en": "In the field: {x}", "hi": "खेत में: {x}", "mr": "शेतात: {x}"},
    "s_reg": {"en": "Registered organic product: {product}, {dose}",
              "hi": "पंजीकृत जैविक उत्पाद: {product}, {dose}",
              "mr": "नोंदणीकृत सेंद्रिय उत्पादन: {product}, {dose}"},
    "s_home": {"en": "Made at home (ICAR / university): {name}, {dose}",
               "hi": "घर पर बनाएँ (आईसीएआर / विश्वविद्यालय): {name}, {dose}",
               "mr": "घरी बनवा (आयसीएआर / विद्यापीठ): {name}, {dose}"},
    "s_nf": {"en": "Natural farming (government guidance, not a registered pesticide): {names}. Ask me how to make it.",
             "hi": "प्राकृतिक खेती (सरकारी मार्गदर्शन, पंजीकृत कीटनाशक नहीं): {names}। इसे बनाने का तरीका मुझसे पूछें।",
             "mr": "नैसर्गिक शेती (सरकारी मार्गदर्शन, नोंदणीकृत कीटकनाशक नाही): {names}. ते कसे बनवायचे ते मला विचारा."},
    "s_chem": {"en": "Chemical, last: {product}, {dose}",
               "hi": "रसायन, आखिर में: {product}, {dose}",
               "mr": "रसायन, शेवटी: {product}, {dose}"},
    "s_avoid": {"en": "Do not: {x}", "hi": "यह न करें: {x}", "mr": "हे करू नका: {x}"},
    "s_sure": {"en": "Not sure it is {name}? Photograph the plant and the app will check.",
               "hi": "पक्का नहीं कि यह {name} है? पौधे की फोटो लें, ऐप जाँच करेगा।",
               "mr": "हे {name} आहे याची खात्री नाही? रोपाचा फोटो घ्या, ॲप तपासेल."},
    "s_also": {"en": "It could also be: {names}.", "hi": "यह यह भी हो सकता है: {names}।",
               "mr": "हे असेही असू शकते: {names}."},
    "s_spray_check": {"en": "Before buying, check the bottle in Spray check.",
                      "hi": "खरीदने से पहले, 'छिड़काव जाँच' में बोतल जाँच लें।",
                      "mr": "खरेदीपूर्वी, 'फवारणी तपासणी' मध्ये बाटली तपासा."},
    "sym_head": {"en": "On {crop}, these show signs like the ones you describe:",
                 "hi": "{crop} में ये समस्याएँ ऐसे ही लक्षण दिखाती हैं:",
                 "mr": "{crop} पिकावर या समस्यांची लक्षणे अशीच दिसतात:"},
    "sym_line": {"en": "{name}: {signature}", "hi": "{name}: {signature}", "mr": "{name}: {signature}"},
    "sym_photo": {"en": "Many look alike. A photo tells them apart, and then the app gives the advice for the one it is.",
                  "hi": "कई एक जैसे दिखते हैं। फोटो से पता चलता है कि कौन-सा है, फिर ऐप उसी की सलाह देता है।",
                  "mr": "अनेक सारखे दिसतात. फोटोवरून कोणता ते कळते, आणि मग ॲप त्याचाच सल्ला देते."},
    "sym_crop": {"en": "Which crop is it on? Tell me the crop, or open your field first, and I can narrow it down.",
                 "hi": "यह किस फसल पर है? फसल बताएँ, या पहले अपना खेत खोलें, फिर मैं ठीक से बता पाऊँगा।",
                 "mr": "हे कोणत्या पिकावर आहे? पीक सांगा, किंवा आधी तुमचे शेत उघडा, मग मी नीट सांगू शकेन."},
    "prod_head": {"en": "Spray check: {product} for {name} on {crop}.",
                  "hi": "छिड़काव जाँच: {crop} में {name} के लिए {product}।",
                  "mr": "फवारणी तपासणी: {name} ({crop}) साठी {product}."},
    "prod_need": {"en": "Which pest or disease do you want to use {product} for? Tell me, and I will check it against the register.",
                  "hi": "{product} किस कीट या रोग के लिए इस्तेमाल करना है? बताएँ, मैं रजिस्टर से जाँच दूँगा।",
                  "mr": "{product} कोणत्या कीड किंवा रोगासाठी वापरायचे आहे? सांगा, मी नोंदणी यादीतून तपासेन."},
    "rec_head": {"en": "How to make {name}:", "hi": "{name} कैसे बनाएँ:", "mr": "{name} कसे बनवायचे:"},
    "rec_dose": {"en": "How much: {dose}", "hi": "कितना: {dose}", "mr": "किती: {dose}"},
    "rec_nf": {"en": "This is natural-farming guidance, not a registered pesticide: use it to prevent, and turn to a registered option if the problem keeps spreading.",
               "hi": "यह प्राकृतिक खेती का मार्गदर्शन है, पंजीकृत कीटनाशक नहीं: इसे बचाव के लिए इस्तेमाल करें, और समस्या फैलती रहे तो पंजीकृत उपाय अपनाएँ।",
               "mr": "हे नैसर्गिक शेतीचे मार्गदर्शन आहे, नोंदणीकृत कीटकनाशक नाही: ते प्रतिबंधासाठी वापरा, आणि समस्या पसरत राहिल्यास नोंदणीकृत उपाय वापरा."},
    "rec_source": {"en": "Source: {source}", "hi": "स्रोत: {source}", "mr": "स्रोत: {source}"},
    "chip_organic": {"en": "Organic options only", "hi": "सिर्फ़ जैविक उपाय", "mr": "फक्त सेंद्रिय उपाय"},
    "chip_ident": {"en": "How do I recognise it?", "hi": "इसे कैसे पहचानें?", "mr": "हे कसे ओळखावे?"},
    "chip_chemical": {"en": "Chemical option", "hi": "रासायनिक उपाय", "mr": "रासायनिक उपाय"},
    "chip_control": {"en": "What should I do?", "hi": "क्या करें?", "mr": "काय करावे?"},
    "go_scan": {"en": "Check with a photo", "hi": "फोटो से जाँचें", "mr": "फोटोने तपासा"},
    "go_spray": {"en": "Open Spray check", "hi": "छिड़काव जाँच खोलें", "mr": "फवारणी तपासणी उघडा"},
}


def _t(key: str, lang: str, **kw) -> str:
    s = tr(TEXT[key], lang)
    return s.format(**kw) if kw else s


def _norm(text: str) -> str:
    from app.krishi import normalise  # noqa: PLC0415  one normaliser for both
    return normalise(text)


def _has(text: str, cues: list[str]) -> bool:
    padded = f" {_norm(text)} "
    return any(f" {_norm(c)} " in padded or (len(c) > 4 and _norm(c) in padded) for c in cues)


def crop_named(text: str) -> str | None:
    """The crop the question names, if exactly one."""
    words = set(_norm(text).split())
    found = {crop for crop, names in CROP_WORDS.items() if any(n in words for n in map(_norm, names))}
    return found.pop() if len(found) == 1 else None


def kind(text: str) -> str:
    """What the farmer wants: a recipe, to recognise it, organic, chemical, or what to do."""
    for k in ("recipe", "identify", "organic", "chemical"):
        if _has(text, CUES[k]):
            return k
    return "control"


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------

def _variants(name: str) -> list[str]:
    """A name and its shorter forms: 'Brown spot (rice)' also as 'brown spot'."""
    out = [name]
    bare = re.sub(r"\s*\(.*?\)", "", name).strip()
    if bare and bare != name:
        out.append(bare)
    return out


@lru_cache(maxsize=4)
def _aliases(kb_id: int) -> dict[str, list[str]]:
    """target id -> every name it goes by, normalised, in every language."""
    kb = _KB_REF[kb_id]
    out: dict[str, set[str]] = {tid: set() for tid in kb.targets}
    for tid, t in kb.targets.items():
        for lang in LANGS:
            for v in _variants(tr(t["names"], lang) or ""):
                n = _norm(v)
                if n:
                    out[tid].add(n)
    for alias, tids in ROMAN.items():
        for tid in tids:
            if tid in out:
                out[tid].add(_norm(alias))
    # The name without its crop word: officers and farmers say "blast", not
    # "rice blast". Not when what is left is one common word ("rust" is on
    # two crops and says nothing about which).
    crop_words = {_norm(w) for ws in CROP_WORDS.values() for w in ws}
    for tid in out:
        for a in list(out[tid]):
            core = " ".join(w for w in a.split() if w not in crop_words)
            if core and core != a and not (len(core.split()) == 1 and core in GENERIC):
                out[tid].add(core)
    return {tid: sorted(v, key=len, reverse=True) for tid, v in out.items()}


_KB_REF: dict[int, KB] = {}


def _register(kb: KB) -> int:
    _KB_REF[id(kb)] = kb
    return id(kb)


def _name_score(alias: str, q_words: list[str], q_padded: str) -> float:
    if f" {alias} " in q_padded:
        return 1.0
    words = alias.split()
    if len(words) < 2:
        # A one-word name has to be there whole, or as the start of an
        # inflected word ("बोंडअळीचा"): a share of one word is nothing.
        return 1.0 if len(alias) >= 4 and any(w.startswith(alias) for w in q_words) else 0.0
    hit = [w for w in words if any(q == w or (len(w) >= 4 and q.startswith(w)) for q in q_words)]
    # Common words alone name nothing ("leaf" is in a dozen names); two of a
    # name's words together ("stem borer") are a name.
    if not hit or (len(hit) < 2 and all(w in GENERIC for w in hit)):
        return 0.0
    return len(hit) / len(words) * 0.9


def distinctive(kb: KB, tid: str, text: str) -> bool:
    """Whether the question names `tid` by a word only its names use, not just
    by common words that also describe ("brown spots" is a description as
    much as it is the disease Brown spot)."""
    q_words = _norm(text).split()
    for alias in _aliases(_register(kb))[tid]:
        if f" {alias} " in f" {' '.join(q_words)} " and len(alias.split()) == 1 and alias not in GENERIC:
            return True
        for w in alias.split():
            if w not in GENERIC and len(w) >= 4 and any(q == w or q.startswith(w) for q in q_words):
                return True
    return False


def without_name(kb: KB, tid: str, text: str) -> str:
    """The question with `tid`'s name taken out: what is left is what the
    farmer says about it ("what to do", or "leaves with grey centres")."""
    name_words = {w for a in _aliases(_register(kb))[tid] for w in a.split()}
    return " ".join(q for q in _norm(text).split()
                    if not any(q == w or (len(w) >= 4 and q.startswith(w)) for w in name_words))


def find(kb: KB, text: str, crop: str | None = None) -> list[tuple[str, float]]:
    """Targets the question names, best first. `crop` keeps only that crop's."""
    q = _norm(text)
    q_words, q_padded = q.split(), f" {q} "
    scores: list[tuple[str, float]] = []
    for tid, names in _aliases(_register(kb)).items():
        if crop and kb.targets[tid]["crop"] != crop:
            continue
        best = max((_name_score(a, q_words, q_padded) for a in names), default=0.0)
        if best >= MIN_NAME:
            # the longer the name that matched, the more specific the match
            scores.append((tid, round(best, 3)))
    return sorted(scores, key=lambda x: -x[1])


# --------------------------------------------------------------------------
# Symptoms
# --------------------------------------------------------------------------

def _features(text: str) -> Counter:
    from app.krishi import features  # noqa: PLC0415
    return features(text)


@lru_cache(maxsize=4)
def _sign_index(kb_id: int):
    """Each target's signs, one document per language: a description is
    scored against the signs in its own language (and English), not against
    all ten run together, which drowned every match."""
    kb = _KB_REF[kb_id]
    docs: dict[tuple[str, str], Counter] = {}
    for tid, t in kb.targets.items():
        if not t.get("signature"):
            continue
        for lang in LANGS:
            text = tr(t["signature"], lang) or ""
            if text:
                docs[(tid, lang)] = _features(text)
    df: Counter = Counter()
    for f in docs.values():
        df.update(f.keys())
    n = len(docs)
    idf = {k: math.log((n + 1) / (v + 1)) + 1 for k, v in df.items()}

    def weigh(f: Counter) -> dict[str, float]:
        v = {k: (1 + math.log(c)) * idf.get(k, 0.0) for k, c in f.items() if k in idf}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {k: x / norm for k, x in v.items()}

    return {key: weigh(f) for key, f in docs.items()}, weigh


def symptoms(kb: KB, text: str, crop: str | None) -> list[tuple[str, float]]:
    """Targets whose signs read like the description, best first."""
    vecs, weigh = _sign_index(_register(kb))
    q = weigh(_features(text))
    if not q:
        return []
    best: dict[str, float] = {}
    for (tid, _lang), v in vecs.items():
        if crop and kb.targets[tid]["crop"] != crop:
            continue
        s = sum(x * v.get(k, 0.0) for k, x in q.items())
        best[tid] = max(best.get(tid, 0.0), s)
    return sorted(((t, round(s, 3)) for t, s in best.items() if s >= MIN_SYMPTOM), key=lambda x: -x[1])


def _model_pick(text: str, candidates: list[str], kb: KB) -> str | None:
    """Which of these the question means, read by the model; checked against the list."""
    if not llm.enabled() or len(candidates) < 2:
        return None
    listing = [(tid, f"{tr(kb.targets[tid]['names'], 'en')} on {kb.targets[tid]['crop']}: "
                     f"{tr(kb.targets[tid].get('signature'), 'en')}") for tid in candidates]
    picked = llm.route(text, listing)
    return picked if picked in candidates else None


# --------------------------------------------------------------------------
# Preparations
# --------------------------------------------------------------------------

PREP_WORDS = {
    "neemastra": ["neemastra", "neemastr", "nimastra", "नीमास्त्र", "निमास्त्र"],
    "agniastra": ["agniastra", "agniastr", "agnyastra", "अग्निअस्त्र", "अग्न्यस्त्र", "अग्निास्त्र"],
    "brahmastra": ["brahmastra", "bramhastra", "brahmastr", "ब्रह्मास्त्र", "ब्रम्हास्त्र"],
    "dashparni_ark": ["dashparni", "dashaparni", "dasparni", "दशपर्णी"],
    "sonthastra": ["sonthastra", "sonthastr", "सोंठास्त्र", "सुंठास्त्र"],
    "khatti_lassi": ["khatti lassi", "sour buttermilk", "khatti chhach", "आंबट ताक", "खट्टी लस्सी", "खट्टी छाछ"],
    "nske_5": ["nske", "neem seed kernel", "nimboli ark", "निंबोळी अर्क", "नीम बीज", "निंबोळी"],
    "pau_neem_extract": ["pau neem", "homemade neem extract", "neem extract"],
}


def prep_named(kb: KB, text: str) -> str | None:
    padded = f" {_norm(text)} "
    for prep, words in PREP_WORDS.items():
        if prep in kb.homemade and any(f" {_norm(w)} " in padded or (len(w) > 5 and _norm(w) in padded) for w in words):
            return prep
    return None


# --------------------------------------------------------------------------
# Answers
# --------------------------------------------------------------------------

def _go(lang: str, spray: bool = False) -> list[dict]:
    out = [{"to": "/app/scan", "label": _t("go_scan", lang)}]
    if spray:
        out.append({"to": "/app/spray", "label": _t("go_spray", lang)})
    return out


def _chips(tid: str, now: str, lang: str) -> list[dict]:
    keys = [k for k in ("control", "organic", "identify", "chemical") if k != now]
    label = {"control": "chip_control", "organic": "chip_organic", "identify": "chip_ident", "chemical": "chip_chemical"}
    return [{"id": f"crop:{tid}:{k}", "text": _t(label[k], lang)} for k in keys][:3]


def _with_field(item: dict) -> str:
    """The standard dose, and the amount for the farmer's own field after it."""
    dose = (item.get("dose") or "").rstrip(". ")
    return f"{dose}. {item['for_field']}" if item.get("for_field") else dose


def pest_answer(kb: KB, tid: str, how: str, lang: str, area: float | None, also: list[str] | None = None) -> dict:
    """What to do about one named target, from its advisory, in `lang`."""
    adv = advisory_engine.compose(kb, tid, lang, area)
    t = kb.targets[tid]
    name, crop = adv["name"], tr(kb.crops[t["crop"]]["names"], lang)
    steps: list[str] = []
    if how == "identify":
        text = _t("p_ident", lang, name=name, crop=crop, signature=adv["signature"])
        steps.append(adv["what_to_check"])
        steps.append(_t("s_sure", lang, name=name))
    else:
        organic_only = how == "organic"
        chem_only = how == "chemical"
        head = "p_organic" if organic_only else "p_chemical" if chem_only else "p_control"
        text = _t(head, lang, name=name, crop=crop)
        field = [r for r in adv["ladder"] if r["tier"] != "chemical"]
        chem = [r for r in adv["ladder"] if r["tier"] == "chemical"]
        recommended = [h for h in adv["homemade"] if h["backing"] != "natural_farming"]
        natural = [h for h in adv["homemade"] if h["backing"] == "natural_farming"]
        if not chem_only:
            # The sourced step first, where there is one: it is the one an
            # extension worker would say.
            field.sort(key=lambda r: 0 if r.get("backing") else 1)
            for r in field[: (2 if organic_only else 1)]:
                steps.append(_t("s_field", lang, x=r["action"]))
            for o in adv["organic"][: (2 if organic_only else 1)]:
                steps.append(_t("s_reg", lang, product=o["product"], dose=_with_field(o)))
            for h in recommended[:1]:
                steps.append(_t("s_home", lang, name=h["name"], dose=_with_field(h)))
            if natural:
                steps.append(_t("s_nf", lang, names=", ".join(h["name"] for h in natural)))
        if not organic_only:
            if chem:
                for r in chem[: (2 if chem_only else 1)]:
                    steps.append(_t("s_chem", lang, product=r["product"], dose=_with_field(r)))
                steps.append(_t("s_spray_check", lang))
            elif adv.get("chemical_none"):
                steps.append(adv["chemical_none"])
        if adv["what_to_avoid"]:
            steps.append(_t("s_avoid", lang, x=adv["what_to_avoid"][0]))
    if also:
        steps.append(_t("s_also", lang, names=", ".join(tr(kb.targets[a]["names"], lang) for a in also)))
    return {"topic": f"crop:{tid}:{how}", "score": 1.0, "text": text, "steps": steps,
            "go": _go(lang, spray=how != "identify"), "suggestions": _chips(tid, how, lang)}


def symptom_answer(kb: KB, cands: list[str], lang: str) -> dict:
    crop = tr(kb.crops[kb.targets[cands[0]]["crop"]]["names"], lang)
    steps = [_t("sym_line", lang, name=tr(kb.targets[c]["names"], lang), signature=tr(kb.targets[c].get("signature"), lang))
             for c in cands]
    steps.append(_t("sym_photo", lang))
    chips = [{"id": f"crop:{c}:control", "text": tr(kb.targets[c]["names"], lang)} for c in cands]
    return {"topic": f"crop:{cands[0]}:symptoms", "score": 1.0, "text": _t("sym_head", lang, crop=crop),
            "steps": steps, "go": _go(lang), "suggestions": chips[:3]}


def recipe_answer(kb: KB, prep: str, lang: str, area: float | None = None) -> dict:
    p = kb.homemade[prep]
    steps = list(trl(p["recipe"], lang))
    if p.get("dose"):
        field = advisory_engine._homemade(kb, {"prep": prep, "timing": {"en": ""}, "source": ""}, lang, area)["for_field"]
        steps.append(_t("rec_dose", lang, dose=tr(p["dose"], lang) + (f" {field}" if field else "")))
    if p.get("backing") == "natural_farming":
        steps.append(_t("rec_nf", lang))
    if p.get("recipe_source"):
        steps.append(_t("rec_source", lang, source=p["recipe_source"]))
    return {"topic": f"prep:{prep}", "score": 1.0, "text": _t("rec_head", lang, name=tr(p["name"], lang)),
            "steps": steps, "go": _go(lang), "suggestions": []}


def product_answer(kb: KB, ingredient: str, tid: str | None, lang: str) -> dict:
    product = kb.pesticides[ingredient]["name"]
    if tid is None:
        return {"topic": "crop:product", "score": 1.0, "text": _t("prod_need", lang, product=product), "steps": [],
                "go": [{"to": "/app/spray", "label": _t("go_spray", lang)}], "suggestions": []}
    t = kb.targets[tid]
    v = labelcheck.check(kb, ingredient, t["crop"], tid, lang)
    return {"topic": f"crop:{tid}:product", "score": 1.0,
            "text": _t("prod_head", lang, product=product, name=tr(t["names"], lang),
                       crop=tr(kb.crops[t["crop"]]["names"], lang)),
            "steps": [v["message"]], "go": [{"to": "/app/spray", "label": _t("go_spray", lang)}],
            "suggestions": _chips(tid, "product", lang)}


def _product_in(kb: KB, text: str) -> str | None:
    """A pesticide the question names as whole words ('neem' in 'neemastra' is not one)."""
    padded = f" {_norm(text)} "
    best, best_len = None, 0
    for pid, p in kb.pesticides.items():
        for n in [p["name"], *p.get("aliases", [])]:
            nn = _norm(n)
            if len(nn) >= 4 and f" {nn} " in padded and len(nn) > best_len:
                best, best_len = pid, len(nn)
    return best


def from_topic(kb: KB, topic: str, lang: str, area: float | None) -> dict | None:
    """A tapped chip: 'crop:<target>:<how>' or 'prep:<prep>'."""
    parts = topic.split(":")
    if parts[0] == "prep" and len(parts) == 2 and parts[1] in kb.homemade:
        return recipe_answer(kb, parts[1], lang, area)
    if parts[0] == "crop" and len(parts) == 3 and parts[1] in kb.targets and parts[2] in (
            "control", "organic", "identify", "chemical"):
        return pest_answer(kb, parts[1], parts[2], lang, area)
    return None


def answer(kb: KB, text: str, lang: str, farm=None, app_score: float = 0.0) -> dict | None:
    """An answer about a pest, disease, product or preparation, or None when the
    question is about none of them (and the app's own topics should answer).

    `app_score` is how well Krishi's own topics matched: a question that is
    plainly about the app ("how do I scan") stays with them."""
    if not (text or "").strip():
        return None
    farm_crop = getattr(farm, "crop", None)
    named_crop = crop_named(text)
    crop = named_crop or farm_crop
    area = getattr(farm, "area_acres", None) if farm is not None and (not named_crop or named_crop == farm_crop) else None
    how = kind(text)

    # A preparation by name: its recipe.
    prep = prep_named(kb, text)
    if prep and (how == "recipe" or not find(kb, text)):
        return recipe_answer(kb, prep, lang, area)

    hits = find(kb, text, named_crop)
    if not hits and named_crop is None and farm_crop:
        hits = []
    if hits and farm_crop and named_crop is None:
        # The farmer's own crop first when the name fits it; another crop's
        # pest is still answered when that is what they named.
        own = [h for h in hits if kb.targets[h[0]]["crop"] == farm_crop]
        hits = own or hits
    product = _product_in(kb, text) if _has(text, PRODUCT_CUES) or how == "chemical" else None

    describing = app_score < 0.30 and _has(text, SYMPTOM_CUES)
    if hits and describing and not distinctive(kb, hits[0][0], text) \
            and _has(without_name(kb, hits[0][0], text), SYMPTOM_CUES):
        # Named only by words that also describe it: read it as a description,
        # and keep the name's own target among the candidates.
        hits_named = [tid for tid, _ in hits]
        if crop is None:
            return {"topic": "crop:need_crop", "score": 1.0, "text": _t("sym_crop", lang), "steps": [],
                    "go": _go(lang), "suggestions": []}
        cands = [tid for tid, _ in symptoms(kb, text, crop)[:4]]
        cands += [t for t in hits_named if t not in cands and kb.targets[t]["crop"] == crop]
        if cands:
            picked = _model_pick(text, cands, kb)
            if picked:
                cands = [picked, *[c for c in cands if c != picked]]
            return symptom_answer(kb, cands[:2], lang)

    if hits and crop is None and not distinctive(kb, hits[0][0], text) \
            and len({kb.targets[t]["crop"] for t, _ in hits}) > 1:
        # "leaf spot" is a disease on every crop: ask which.
        return {"topic": "crop:need_crop", "score": 1.0, "text": _t("sym_crop", lang), "steps": [],
                "go": _go(lang), "suggestions": []}

    if hits:
        top = hits[0][1]
        best = [tid for tid, s in hits if s >= top - 1e-9]
        if len(best) > 1:
            picked = _model_pick(text, best, kb)
            if picked:
                best = [picked, *[b for b in best if b != picked]]
        tid = best[0]
        if top < 1.0 and app_score >= 0.45:
            return None  # a partial name inside a plain app question
        if product and _has(text, PRODUCT_CUES):
            return product_answer(kb, product, tid, lang)
        also = [b for b in best[1:3] if kb.targets[b]["crop"] == kb.targets[tid]["crop"]]
        return pest_answer(kb, tid, how, lang, area, also)

    if product and _has(text, PRODUCT_CUES):
        return product_answer(kb, product, None, lang)

    # No name: a description of what the farmer sees.
    if describing:
        if crop is None:
            cands = symptoms(kb, text, None)
            if cands:
                return {"topic": "crop:need_crop", "score": 1.0, "text": _t("sym_crop", lang), "steps": [],
                        "go": _go(lang), "suggestions": []}
            return None
        cands = [tid for tid, _ in symptoms(kb, text, crop)[:4]]
        if not cands:
            # Nothing in the signs matched the words — Hindi or Marathi in Latin
            # letters, say. The model reads it against this crop's own list.
            own = [tid for tid, t in kb.targets.items() if t["crop"] == crop and t.get("signature")]
            picked = _model_pick(text, own, kb)
            if not picked:
                return None
            # A second reading, so the farmer sees what else it could be.
            second = _model_pick(text, [t for t in own if t != picked], kb)
            return symptom_answer(kb, [picked, *([second] if second else [])], lang)
        picked = _model_pick(text, cands, kb)
        if picked:
            cands = [picked, *[c for c in cands if c != picked]]
        return symptom_answer(kb, cands[:2], lang)
    return None
