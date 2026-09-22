"""Krishi, the in-app helper.

Krishi answers questions about the app itself — how to check a plant, what a
screen or an alert means — and a few about the farmer's own field right now
(can I spray, will it rain, should I water, what did the expert say). It is
grounded, not generative: every answer is either an authored topic from
kb/krishi.json or a sentence built from the same data the screens show. When a
question matches nothing well enough it says so and offers the Kisan Call
Centre, rather than inventing an answer. It never names a pesticide.

Matching is TF-IDF over word and character-trigram features of each topic's
example questions and keywords in every language (so "spray kab karu" and
"फवारणी कधी करू" both land on the spray window), with a small boost for
topics about the screen the farmer is on.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cache, nim, services, voice
from app.i18n import local_date
from app.config import KB_DIR
from app.engine import agromet, agroweather
from app.i18n import LANGS
from app.kb import KB, tr, trl
from app.models import Alert, Farm, FarmerProfile, FollowUp, Problem

MATCH_MIN = 0.14
"""Below this similarity Krishi says it didn't understand instead of guessing."""
CONFIDENT = 0.30
CLEAR_LEAD = 0.08
"""The native+English score answers alone only this far ahead of the runner-up;
a close call goes to the model."""
"""At or above this the matcher is trusted on its own and no model is called:
the common questions stay instant and work with the network down."""
PERSONAL = "my_details"
"""Not an authored topic — the id the router returns for "what crops do I grow",
"where is my field", "how much land do I have". Answered from the signed-in
farmer's own rows and nothing else (see `facts` and `_personal`)."""
SCREEN_BOOST = 0.05
KEYWORD_BOOST = 0.08
FARM_TOPICS = ("today", "weather_now", "spray_now", "irrigate_now", "risks_now", "my_cases", "my_farm")
"""Answered from the farmer's own field: they need a farm open."""
LIVE_TOPICS = (*FARM_TOPICS, "crop_support")
AUTHORED_LANGS = ("en", "hi", "mr")

# What each screen offers first, as suggestion chips.
SCREEN_CHIPS = {
    "home": ["today", "scan_photo", "weather_now", "live_check"],
    "scan": ["scan_photo", "photo_tips", "live_check", "crop_support"],
    "live": ["live_check", "photo_tips"],
    "result": ["confidence", "advice_ladder", "expert_wait", "spray_check"],
    "weather": ["spray_now", "irrigate_now", "spray_window", "weather_screen"],
    "spray": ["spray_check", "spray_now", "never_safe", "which_pesticide"],
    "alerts": ["today", "notifications", "traps", "alert_levels"],
    "history": ["my_cases", "followup", "expert_wait", "history"],
    "onboard": ["switch_farm", "language", "crop_support", "what_is_app"],
    "login": ["no_code", "signup_email", "signup_role", "privacy"],
    "signup": ["signup_role", "signup_email", "signup_location", "soil_card"],
}

# Sentences Krishi builds from live data. Other languages come from the
# translation memory (translate_i18n.py reads this module).
TEXT = {
    "hello": {"en": "Namaste{name}! I'm Krishi. Ask me anything about the app, or tap a question.",
              "hi": "नमस्ते{name}! मैं कृषि हूँ। ऐप के बारे में कुछ भी पूछें, या कोई सवाल दबाएँ।",
              "mr": "नमस्कार{name}! मी कृषी. ॲपबद्दल काहीही विचारा, किंवा एखादा प्रश्न दाबा."},
    "not_sure": {"en": "Sorry, I didn't understand that. I help with using AnnRakshak — try one of these, or ask in other words. "
                       "For anything else, call the Kisan Call Centre on 1800-180-1551 (free).",
                 "hi": "माफ़ कीजिए, मैं समझ नहीं पाया। मैं AnnRakshak चलाने में मदद करता हूँ — इनमें से कोई चुनें, या दूसरे शब्दों में पूछें। "
                       "बाकी किसी बात के लिए किसान कॉल सेंटर 1800-180-1551 (निःशुल्क) पर फ़ोन करें।",
                 "mr": "माफ करा, मला समजले नाही. मी AnnRakshak वापरण्यात मदत करतो — यापैकी एखादा निवडा, किंवा वेगळ्या शब्दांत विचारा. "
                       "इतर कशासाठीही किसान कॉल सेंटर 1800-180-1551 (मोफत) वर फोन करा."},
    "need_farm": {"en": "Open one of your fields first, then I can answer that from its weather and crop.",
                  "hi": "पहले अपना कोई खेत खोलें, फिर मैं उसके मौसम और फसल से इसका जवाब दे पाऊँगा।",
                  "mr": "आधी तुमचे एखादे शेत उघडा, मग मी त्याच्या हवामान आणि पिकावरून याचे उत्तर देऊ शकेन."},
    "no_weather": {"en": "Weather for your field isn't reachable right now. Try again in a little while, or open Weather.",
                   "hi": "अभी आपके खेत का मौसम नहीं मिल रहा। थोड़ी देर में फिर कोशिश करें, या मौसम खोलें।",
                   "mr": "सध्या तुमच्या शेताचे हवामान मिळत नाही. थोड्या वेळाने पुन्हा प्रयत्न करा, किंवा हवामान उघडा."},
    "today_intro": {"en": "Today for your {crop} ({stage}, day {das}):",
                    "hi": "आज आपकी {crop} के लिए ({stage}, दिन {das}):",
                    "mr": "आज तुमच्या {crop} साठी ({stage}, दिवस {das}):"},
    "today_alert": {"en": "Check for {name}: {task}", "hi": "{name} के लिए देखें: {task}",
                    "mr": "{name} साठी तपासा: {task}"},
    "today_followup": {"en": "Tell us how your crop is after treating {name} (Better / Same / Worse on Home).",
                       "hi": "{name} के इलाज के बाद फसल कैसी है, बताएँ (होम पर बेहतर / वैसी ही / बदतर)।",
                       "mr": "{name} वरील उपचारानंतर पीक कसे आहे ते सांगा (होमवर बरे / तसेच / वाईट)."},
    "today_calm": {"en": "No field checks are due and there are no weather warnings. A normal walk through the field is enough today.",
                   "hi": "कोई खेत जाँच बाकी नहीं है और मौसम की कोई चेतावनी नहीं है। आज खेत में सामान्य चक्कर काफ़ी है।",
                   "mr": "कोणतीही शेत तपासणी बाकी नाही आणि हवामानाचा इशारा नाही. आज शेतात साधी फेरी पुरेशी आहे."},
    "weather_line": {"en": "Right now {temp}°C, humidity {rh}%, {prob}% chance of rain in the next 3 hours.",
                     "hi": "अभी {temp}°C, नमी {rh}%, अगले 3 घंटों में बारिश की संभावना {prob}%।",
                     "mr": "आत्ता {temp}°C, आर्द्रता {rh}%, पुढच्या 3 तासांत पावसाची शक्यता {prob}%."},
    "weather_days": {"en": "Next 3 days: about {mm} mm of rain in all.",
                     "hi": "अगले 3 दिन: कुल लगभग {mm} मिमी बारिश।",
                     "mr": "पुढील 3 दिवस: एकूण सुमारे {mm} मिमी पाऊस."},
    "weather_dry": {"en": "Next 3 days: little or no rain expected.", "hi": "अगले 3 दिन: बारिश कम या नहीं।",
                    "mr": "पुढील 3 दिवस: पाऊस कमी किंवा नाही."},
    "spray_good": {"en": "Yes — now is a good time to spray.", "hi": "हाँ — अभी छिड़काव का अच्छा समय है।",
                   "mr": "हो — आत्ता फवारणीसाठी चांगली वेळ आहे."},
    "spray_caution": {"en": "You can spray now, but with care: {why}.", "hi": "अभी छिड़काव कर सकते हैं, पर सावधानी से: {why}।",
                      "mr": "आत्ता फवारणी करू शकता, पण काळजीपूर्वक: {why}."},
    "spray_avoid": {"en": "No — don't spray now: {why}.", "hi": "नहीं — अभी छिड़काव न करें: {why}।",
                    "mr": "नाही — आत्ता फवारणी करू नका: {why}."},
    "spray_next": {"en": "Next good time: {when}.", "hi": "अगला अच्छा समय: {when}।", "mr": "पुढची चांगली वेळ: {when}."},
    "spray_none": {"en": "There's no good spraying window in the next 48 hours.",
                   "hi": "अगले 48 घंटों में छिड़काव का कोई अच्छा समय नहीं है।",
                   "mr": "पुढच्या 48 तासांत फवारणीसाठी चांगली वेळ नाही."},
    "spray_first": {"en": "Before any spray, check the product in Spray check.",
                    "hi": "कोई भी छिड़काव करने से पहले 'छिड़काव' जाँच में दवा जाँच लें।",
                    "mr": "कोणतीही फवारणी करण्यापूर्वी 'फवारणी' तपासणीत औषध तपासा."},
    "today": {"en": "today", "hi": "आज", "mr": "आज"},
    "tomorrow": {"en": "tomorrow", "hi": "कल", "mr": "उद्या"},
    "water_irrigate": {"en": "Yes, your {crop} likely needs water: it used about {etc} mm this week and useful rain gave {rain} mm. "
                             "Check that the soil is dry 5 cm down, then irrigate.",
                       "hi": "हाँ, आपकी {crop} को शायद पानी चाहिए: इस हफ़्ते उसने लगभग {etc} मिमी पानी लिया और काम की बारिश {rain} मिमी हुई। "
                             "देखें कि मिट्टी 5 सेमी नीचे तक सूखी है, फिर सिंचाई करें।",
                       "mr": "हो, तुमच्या {crop} ला बहुधा पाणी हवे: या आठवड्यात त्याने सुमारे {etc} मिमी पाणी वापरले आणि उपयोगी पाऊस {rain} मिमी झाला. "
                             "माती 5 सेमी खोलपर्यंत कोरडी आहे का ते पाहा, मग पाणी द्या."},
    "water_hold_rain": {"en": "Hold irrigation — useful rain is expected in the next 3 days ({mm} mm).",
                        "hi": "सिंचाई रोकें — अगले 3 दिनों में काम की बारिश ({mm} मिमी) की उम्मीद है।",
                        "mr": "सिंचन थांबवा — पुढच्या 3 दिवसांत उपयोगी पाऊस ({mm} मिमी) अपेक्षित आहे."},
    "water_ok": {"en": "No irrigation needed now — the week's rain has covered what your crop used.",
                 "hi": "अभी सिंचाई की ज़रूरत नहीं — हफ़्ते की बारिश ने फसल की ज़रूरत पूरी कर दी है।",
                 "mr": "आत्ता सिंचनाची गरज नाही — आठवड्याच्या पावसाने पिकाची गरज भागवली आहे."},
    "water_stop_stage": {"en": "Your crop is maturing — irrigation is normally stopped at this stage.",
                         "hi": "फसल पक रही है — इस अवस्था में आम तौर पर सिंचाई बंद कर दी जाती है।",
                         "mr": "पीक पक्व होत आहे — या अवस्थेत सहसा सिंचन थांबवले जाते."},
    "water_unknown": {"en": "There isn't enough recent weather for your field to judge water yet. Push a finger 5 cm into the soil: if it's dry, irrigate.",
                      "hi": "आपके खेत के पानी का अंदाज़ा लगाने के लिए अभी पर्याप्त मौसम आँकड़े नहीं हैं। मिट्टी में 5 सेमी उंगली डालें: सूखी हो तो सिंचाई करें।",
                      "mr": "तुमच्या शेताच्या पाण्याचा अंदाज लावण्यासाठी अद्याप पुरेशी हवामान माहिती नाही. मातीत 5 सेमी बोट घाला: कोरडी असेल तर पाणी द्या."},
    "risks_intro": {"en": "The weather and your crop's growth stage favour these now:",
                    "hi": "अभी का मौसम और फसल की अवस्था इनके लिए अनुकूल है:",
                    "mr": "सध्याचे हवामान आणि पिकाची अवस्था यांना पोषक आहे:"},
    "risks_none": {"en": "Nothing is favoured strongly right now. AnnRakshak keeps checking every day and will alert you.",
                   "hi": "अभी कोई कीट या रोग ज़्यादा अनुकूल नहीं है। AnnRakshak रोज़ जाँचता रहता है और आपको अलर्ट करेगा।",
                   "mr": "सध्या कोणतीही कीड किंवा रोग जास्त पोषक नाही. AnnRakshak रोज तपासत राहते आणि तुम्हाला सूचना देईल."},
    "level_high": {"en": "high risk", "hi": "अधिक जोखिम", "mr": "जास्त धोका"},
    "level_medium": {"en": "risk", "hi": "जोखिम", "mr": "धोका"},
    "level_low": {"en": "watch", "hi": "नज़र रखें", "mr": "लक्ष ठेवा"},
    "cases_none": {"en": "You haven't reported any problems on this field yet. Photograph a sick plant to start.",
                   "hi": "आपने इस खेत पर अभी कोई समस्या दर्ज नहीं की है। शुरू करने के लिए बीमार पौधे की फोटो लें।",
                   "mr": "तुम्ही या शेतावर अद्याप कोणतीही समस्या नोंदवली नाही. सुरुवात करण्यासाठी आजारी रोपाचा फोटो घ्या."},
    "cases_intro": {"en": "Your latest problems:", "hi": "आपकी हाल की समस्याएँ:", "mr": "तुमच्या अलीकडील समस्या:"},
    "case_waiting": {"en": "{name}: waiting for an expert — number {pos} in the queue, about {eta} min.",
                     "hi": "{name}: विशेषज्ञ का इंतज़ार — कतार में {pos}वाँ, लगभग {eta} मिनट।",
                     "mr": "{name}: तज्ज्ञांची प्रतीक्षा — रांगेत {pos} वा, सुमारे {eta} मिनिटे."},
    "case_confirmed": {"en": "{name}: confirmed by {expert}.", "hi": "{name}: {expert} ने पुष्टि की।",
                       "mr": "{name}: {expert} यांनी खात्री केली."},
    "case_corrected": {"en": "{name}: corrected by {expert}.", "hi": "{name}: {expert} ने सुधारा।",
                       "mr": "{name}: {expert} यांनी दुरुस्त केले."},
    "case_advised": {"en": "{name}: advice given — see What to do.", "hi": "{name}: सलाह दी गई — 'क्या करें' देखें।",
                     "mr": "{name}: सल्ला दिला — 'काय करावे' पहा."},
    "case_open": {"en": "{name}: open.", "hi": "{name}: खुली है।", "mr": "{name}: चालू आहे."},
    "case_resolved": {"en": "{name}: resolved.", "hi": "{name}: सुलझ गई।", "mr": "{name}: सुटली."},
    "case_unknown": {"en": "Photo sent for checking", "hi": "जाँच के लिए भेजी गई फोटो", "mr": "तपासणीसाठी पाठवलेला फोटो"},
    "case_note": {"en": "Expert's note: {note}", "hi": "विशेषज्ञ की टिप्पणी: {note}", "mr": "तज्ज्ञांची टीप: {note}"},
    "crops_photo": {"en": "A photo or a live check identifies diseases and pests on {crops}.",
                    "hi": "फोटो या लाइव जाँच {crops} के रोग और कीट पहचानती है।",
                    "mr": "फोटो किंवा थेट तपासणी {crops} चे रोग व किडी ओळखते."},
    "crops_other": {"en": "{crops}: everything else works — weather warnings, pest-risk alerts, trap counts, spray "
                          "and water advice — and you can send close-ups to an expert. Photo checks for them are being added.",
                    "hi": "{crops}: बाकी सब चलता है — मौसम चेतावनी, कीट-खतरे के अलर्ट, ट्रैप गिनती, छिड़काव और पानी की सलाह — "
                          "और आप पास की फोटो विशेषज्ञ को भेज सकते हैं। इनकी फोटो जाँच जोड़ी जा रही है।",
                    "mr": "{crops}: बाकी सर्व चालते — हवामान इशारे, किडीच्या धोक्याच्या सूचना, सापळा नोंद, फवारणी व पाण्याचा सल्ला — "
                          "आणि जवळचे फोटो तज्ज्ञांना पाठवता येतात. त्यांची फोटो तपासणी जोडली जात आहे."},
    "crops_trained": {"en": "The model is trained on ICAR photos and field photos from Indian fields.",
                      "hi": "मॉडल ICAR की तस्वीरों और भारतीय खेतों की फ़ील्ड फ़ोटो पर सीखा है।",
                      "mr": "मॉडेल ICAR ची चित्रे आणि भारतीय शेतांतील फोटोंवर शिकले आहे."},
    "farm_line": {"en": "Crop: {crop}. Place: {place}. Sown on {sown}. Age: {das} days. Stage: {stage}. Field: {area} acres.",
                  "hi": "फसल: {crop}। जगह: {place}। बुवाई: {sown}। उम्र: {das} दिन। अवस्था: {stage}। खेत: {area} एकड़।",
                  "mr": "पीक: {crop}. ठिकाण: {place}. पेरणी: {sown}. वय: {das} दिवस. अवस्था: {stage}. क्षेत्र: {area} एकर."},
}

# Buttons Krishi attaches to live answers.
GO = {
    "home": {"to": "/app", "label": {"en": "Open Home", "hi": "होम खोलें", "mr": "होम उघडा"}},
    "weather": {"to": "/app/weather", "label": {"en": "Open Weather", "hi": "मौसम खोलें", "mr": "हवामान उघडा"}},
    "alerts": {"to": "/app/alerts", "label": {"en": "Open Alerts", "hi": "अलर्ट खोलें", "mr": "सूचना उघडा"}},
    "spray": {"to": "/app/spray", "label": {"en": "Open Spray check", "hi": "छिड़काव जाँच खोलें",
                                            "mr": "फवारणी तपासणी उघडा"}},
    "scan": {"to": "/app/scan", "label": {"en": "Open Scan", "hi": "जाँच खोलें", "mr": "तपासणी उघडा"}},
    "history": {"to": "/app/history", "label": {"en": "Open History", "hi": "इतिहास खोलें", "mr": "इतिहास उघडा"}},
}


def _today_ist() -> date:
    """India's date, as every other screen uses (agroweather.now_ist). The
    server's own clock may run on UTC, which is still "yesterday" for the first
    five and a half hours of an Indian morning."""
    return agroweather.now_ist().date()


def _t(key: str, lang: str, **kw) -> str:
    return tr(TEXT[key], lang).format(**kw)


# --------------------------------------------------------------------------
# Knowledge base and index
# --------------------------------------------------------------------------

def load() -> dict:
    return json.loads((KB_DIR / "krishi.json").read_text(encoding="utf-8"))


def validate(data: dict) -> list[str]:
    """Problems with kb/krishi.json; the app refuses to start on any."""
    errors: list[str] = []
    screens, routes = set(data["screens"]), set(data["routes"])
    ids = [t["id"] for t in data["topics"]]
    if len(ids) != len(set(ids)):
        errors.append("duplicate topic ids")
    for t in data["topics"]:
        tid = t["id"]
        live = t.get("live", False)
        if live and tid not in LIVE_TOPICS:
            errors.append(f"{tid}: marked live but no live answer is implemented")
        if not live and not all(t.get("answer", {}).get(lang) for lang in AUTHORED_LANGS):
            errors.append(f"{tid}: answer missing in one of {AUTHORED_LANGS}")
        if not all(t.get("ask", {}).get(lang) for lang in AUTHORED_LANGS):
            errors.append(f"{tid}: example questions missing in one of {AUTHORED_LANGS}")
        if "steps" in t and not all(t["steps"].get(lang) for lang in AUTHORED_LANGS):
            errors.append(f"{tid}: steps missing in one of {AUTHORED_LANGS}")
        for s in t["screens"]:
            if s not in screens:
                errors.append(f"{tid}: unknown screen {s}")
        for g in t.get("go", []):
            if g["to"] not in routes or not all(g["label"].get(lang) for lang in AUTHORED_LANGS):
                errors.append(f"{tid}: bad button {g}")
    known = set(ids)
    for screen, chips in SCREEN_CHIPS.items():
        errors += [f"chip {c} on {screen}: no such topic" for c in chips if c not in known]
    return errors


_SPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Lower case, NFC, punctuation and symbols to spaces. Keeps letters, marks
    (Indic vowel signs) and digits of every script."""
    text = unicodedata.normalize("NFC", text or "").lower()
    out = "".join(" " if unicodedata.category(ch)[0] in "PSZC" else ch for ch in text)
    return _SPACE.sub(" ", out).strip()


# Words that carry no meaning for matching (question filler in English,
# Hindi, Marathi and their romanised spellings).
STOP = frozenset("""
a an the is are am was were be to of in on at for with and or my me i you your it this that these those do does
did can could should would will shall how what why when where which who please tell about there here any some
kya kyu kyon hai hain ka ki ke ko se me mein mai main mera meri mere tum aap kar karo karna aur ya bhi ho hoga
kay kaay aahe ahe ka ki la na ne va ani mi majha majhi maze tumhi kasa kashi kase kiti
क्या है हैं का की के को से में मैं मेरा मेरी मेरे आप कर करें और या भी हो
काय आहे आहेत का ची चा चे ला ने व आणि मी माझा माझी माझे तुम्ही कसा कशी कसे
""".split())


def features(text: str) -> Counter:
    words = [w for w in normalise(text).split() if w not in STOP]
    f: Counter = Counter()
    for w in words:
        f["w:" + w] += 1
        padded = f" {w} "
        if len(w) < 3:
            continue
        for i in range(len(padded) - 2):
            f[padded[i:i + 3]] += 1
    return f


class Index:
    def __init__(self, topics: list[dict]):
        self.topics = {t["id"]: t for t in topics}
        docs: dict[str, Counter] = {}
        self.keys: dict[str, set[str]] = {}
        for t in topics:
            text = []
            for lang in LANGS:  # machine languages come from the translation memory
                text += trl(t["ask"], lang) if lang not in AUTHORED_LANGS else t["ask"].get(lang, [])
            text += t.get("keys", [])
            docs[t["id"]] = features(" . ".join(text))
            self.keys[t["id"]] = {normalise(k) for k in t.get("keys", []) if normalise(k)}
        df: Counter = Counter()
        for f in docs.values():
            df.update(f.keys())
        n = len(docs)
        self.idf = {k: math.log((n + 1) / (v + 1)) + 1 for k, v in df.items()}
        self.vecs = {tid: self._weigh(f) for tid, f in docs.items()}

    def _weigh(self, f: Counter) -> dict[str, float]:
        v = {k: (1 + math.log(c)) * self.idf.get(k, 0.0) for k, c in f.items() if k in self.idf}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {k: x / norm for k, x in v.items()}

    def rank(self, query: str, screen: str | None) -> list[tuple[str, float]]:
        q = self._weigh(features(query))
        if not q:
            return []
        words = f" {normalise(query)} "
        scores = []
        for tid, v in self.vecs.items():
            s = sum(x * v.get(k, 0.0) for k, x in q.items())
            if any(f" {k} " in words for k in self.keys[tid]):
                s += KEYWORD_BOOST
            if screen and screen in self.topics[tid]["screens"]:
                s += SCREEN_BOOST
            scores.append((tid, round(s, 4)))
        return sorted(scores, key=lambda x: -x[1])


@lru_cache(maxsize=1)
def index() -> Index:
    data = load()
    errors = validate(data)
    if errors:
        raise ValueError("kb/krishi.json: " + "; ".join(errors))
    return Index(data["topics"])


# --------------------------------------------------------------------------
# Answers
# --------------------------------------------------------------------------

def _chip(t: dict, lang: str) -> dict:
    return {"id": t["id"], "text": (trl(t["ask"], lang) if lang not in AUTHORED_LANGS else t["ask"][lang])[0]}


def _go(items: list[dict], lang: str) -> list[dict]:
    return [{"to": g["to"], "label": tr(g["label"], lang)} for g in items]


def suggestions(screen: str | None, lang: str, exclude: tuple[str, ...] = ()) -> list[dict]:
    idx = index()
    ids = SCREEN_CHIPS.get(screen or "", SCREEN_CHIPS["home"])
    return [_chip(idx.topics[i], lang) for i in ids if i not in exclude][:4]


def hello(screen: str | None, lang: str, name: str | None) -> dict:
    first = name.split()[0] if name and not name.lower().startswith("demo") else ""
    return {"text": _t("hello", lang, name=f" {first}" if first else ""), "suggestions": suggestions(screen, lang)}


# --------------------------------------------------------------------------
# Answering in the farmer's own voice
# --------------------------------------------------------------------------

SCRIPTS = [  # Unicode block -> language
    ((0x0980, 0x09FF), "bn"), ((0x0A00, 0x0A7F), "pa"), ((0x0A80, 0x0AFF), "gu"), ((0x0B80, 0x0BFF), "ta"),
    ((0x0C00, 0x0C7F), "te"), ((0x0C80, 0x0CFF), "kn"), ((0x0D00, 0x0D7F), "ml"), ((0x0900, 0x097F), "deva"),
]

ROMAN = {  # everyday words farmers type in English letters, per language
    "hi": "kya kyaa hai h hain hoga hogi aaj aj kal mera meri mere kab karu karoon karna nahi nhi kaise kitna "
          "kitni ka ki ke ko mein mausam barish baarish dawa dawai khet fasal paani pani chhidkav kyu kyun "
          "batao bata sakta sakte abhi raha rahi gaya kaun konsi",
    "mr": "kay kaay ahe aahe majha majhi maza mazi kadhi kasa kashi paus sheti pik kiti karaycha udya "
          "fawarni favarni havaman zala nahi",
    "bn": "ache achhe amar amake kobe kemon kothay kichu brishti chas jol korbo hobe bolo keno",
    "ta": "enna epdi eppadi naan enaku inniku indru naalai mazhai vayal payir thanni eppo sollu iruku irukku",
    "te": "emi ela naaku ivala eeroju repu varsham panta polam neellu eppudu cheppu undi ledu",
    "kn": "enu hege nanna nange indu naale male bele hola neeru yavaga heli ide",
    "ml": "enthu entha engane ente enikku innu mazha vila vellam eppol parayu undo",
    "gu": "shu kem che chhe maru mari aaje kale varsad khetar paak kyare kaho nathi",
    "pa": "kiven ajj meenh kado dasso kinna",
}
_ROMAN = {lang: set(words.split()) for lang, words in ROMAN.items()}


def register(text: str | None, app_lang: str) -> tuple[str, bool]:
    """The language the farmer wrote in, and whether in English letters.

    An Indian script decides the language (Devanagari follows the app between
    Hindi and Marathi). English letters are English unless the words are a
    romanised Indian language ("aj ka weather kya h" is Hindi); a tie goes to
    the app's language. No question text (a tapped chip): the app's language."""
    s = (text or "").strip()
    if not s:
        return app_lang, False
    counts: Counter = Counter()
    latin = 0
    for ch in s:
        o = ord(ch)
        if ch.isascii() and ch.isalpha():
            latin += 1
            continue
        for (lo, hi), code in SCRIPTS:
            if lo <= o <= hi:
                counts[code] += 1
                break
    if counts and counts.most_common(1)[0][1] >= latin:
        code = counts.most_common(1)[0][0]
        if code == "deva":
            code = app_lang if app_lang in ("hi", "mr") else "hi"
        return code, False
    words = set(re.findall(r"[a-z]+", s.lower()))
    scores = {lang: len(words & vocab) for lang, vocab in _ROMAN.items()}
    top = max(scores.values())
    if top == 0:
        return "en", False
    tied = [lang for lang, n in scores.items() if n == top]
    return (app_lang if app_lang in tied else tied[0]), True


def answer(db: Session, kb: KB, *, text: str | None, topic: str | None, screen: str | None, lang: str,
           farm: Farm | None, user=None, farms: list[Farm] | None = None) -> dict:
    """Answer in the language and letters the farmer used: a Tamil question gets
    Tamil, English gets English, and "aj ka weather kya h" gets Hindi in English
    letters. `speak` keeps the proper-script text for the voice."""
    said, roman = register(text, lang)
    out = _answer(db, kb, text=text, topic=topic, screen=screen, lang=said, farm=farm, user=user, farms=farms)
    out["lang"] = said
    if roman and said != "en":
        native = [out.get("text") or "", *(out.get("steps") or [])]
        styled = nim.restyle(text or "", native, said)
        if styled:
            out["speak"] = " ".join(x for x in native if x)
            out["text"], out["steps"] = styled[0], styled[1:]
    return out


def _answer(db: Session, kb: KB, *, text: str | None, topic: str | None, screen: str | None, lang: str,
            farm: Farm | None, user=None, farms: list[Farm] | None = None) -> dict:
    """`user` and `farms` are the signed-in farmer and their own fields, and are
    the only place a personal answer may come from."""
    idx = index()
    ranked: list[tuple[str, float]] = []
    if topic in idx.topics:
        best, score = topic, 1.0
    elif topic == PERSONAL:
        best, score = PERSONAL, 1.0
    else:
        ranked = idx.rank(text or "", screen)
        best, score = ranked[0] if ranked else (None, 0.0)
        # A machine-translated language: the keyword lists there are thin, so
        # the question is also read in English (Bhashini, ~0.5 s) and each
        # topic scores on both. A clear winner skips the model entirely — which
        # also keeps Krishi answering when the model is slow or down.
        fused: list[tuple[str, float]] = []
        if score < CONFIDENT and lang not in AUTHORED_LANGS and (text or "").strip():
            fused = _fused_rank(idx, text or "", lang, screen)
            runner_up = fused[1][1] if len(fused) > 1 else 0.0
            if fused and fused[0][1] >= CONFIDENT and fused[0][1] - runner_up >= CLEAR_LEAD:
                ranked, (best, score) = fused, fused[0]
        # The matcher is fast, offline and right about the common questions. It
        # is weak on the way farmers really type ("mera dhan me patta pila ho
        # raha hai"), so below CONFIDENT the model reads the question instead —
        # and only ever answers with one of our own topic ids.
        if score < CONFIDENT and (text or "").strip():
            routed = _route(text or "", idx)
            if routed in idx.topics:
                best, score, ranked = routed, max(score, MATCH_MIN), []
            elif routed == PERSONAL:
                best, score, ranked = PERSONAL, 1.0, []
            elif routed is None and fused and fused[0][1] >= CONFIDENT and not nim.answered_none():
                ranked, (best, score) = fused, fused[0]  # the model is down: the close call stands
            elif routed is None and score < MATCH_MIN:
                best = None  # off topic, or nothing we have an authored answer for
    if best == PERSONAL:
        out = _personal(db, kb, user, farms or [], text or "", lang, screen)
        if out is not None:
            return out
        best, score = (ranked[0] if ranked else (None, 0.0))
    if best is None or score < MATCH_MIN:
        return {"topic": None, "score": score, "text": _t("not_sure", lang), "steps": [],
                "go": [], "suggestions": suggestions(screen, lang)}
    t = idx.topics[best]
    if t.get("live"):
        body = _live(db, kb, best, lang, farm)
    else:
        body = {"text": tr(t["answer"], lang), "steps": trl(t["steps"], lang) if "steps" in t else [],
                "go": _go(t.get("go", []), lang)}
    # Other close matches first ("did you mean"), then the screen's own chips.
    near = [tid for tid, s in ranked[1:4] if s >= MATCH_MIN and tid != best]
    more = [_chip(idx.topics[tid], lang) for tid in near]
    more += [c for c in suggestions(screen, lang, exclude=(best, *near))]
    return {"topic": best, "score": score, **body, "suggestions": more[:4]}


def _live(db: Session, kb: KB, topic: str, lang: str, farm: Farm | None) -> dict:
    if topic == "crop_support":
        return _crops(kb, lang)
    if farm is None:
        return {"text": _t("need_farm", lang), "steps": [], "go": []}
    fn = {"today": _today, "weather_now": _weather, "spray_now": _spray, "irrigate_now": _water,
          "risks_now": _risks, "my_cases": _cases, "my_farm": _farm_line}[topic]
    return fn(db, kb, farm, lang)


def _crops(kb: KB, lang: str) -> dict:
    """Which crops the camera can identify — read from the knowledge base, so it
    is right the day a crop's photo model ships."""
    def names(want: bool) -> str:
        return ", ".join(tr(c["names"], lang) for c in kb.crops.values() if c["photo_diagnosis"] is want)

    text = _t("crops_photo", lang, crops=names(True)) + " " + _t("crops_trained", lang)
    rest = names(False)
    steps = [_t("crops_other", lang, crops=rest)] if rest else []
    return {"text": text, "steps": steps, "go": _go([GO["scan"]], lang)}


def _weather_view(db: Session, kb: KB, farm: Farm, lang: str) -> dict | None:
    try:
        b = agroweather.bundle(farm.lat, farm.lon)
    except agroweather.AgroWeatherUnavailable:
        return None
    from app import notify  # noqa: PLC0415  (imports the push stack; only needed here)

    now = agroweather.now_ist()
    stage, _ = kb.stage_for(farm.crop, farm.sowing_date, now.date())
    return agromet.view(b, kb.agromet, farm.crop, stage, now, lang, sprays=notify.recent_sprays(db, farm, now),
                        needs_spray=notify.needs_spray(db, farm))


def _crop(kb: KB, farm: Farm, lang: str) -> str:
    return tr(kb.crops[farm.crop]["names"], lang)


def _today(db: Session, kb: KB, farm: Farm, lang: str) -> dict:
    today = _today_ist()
    stage, das = kb.stage_for(farm.crop, farm.sowing_date, today)
    steps: list[str] = []
    alerts = db.scalars(select(Alert).where(Alert.farm_id == farm.id, Alert.outcome.is_(None),
                                            Alert.issued_on >= today - timedelta(days=2))
                        .order_by(Alert.issued_on.desc(), Alert.id.desc())).all()
    seen: set[str] = set()
    for a in alerts:
        if a.target in seen or a.target not in kb.targets:
            continue
        seen.add(a.target)
        tasks = trl(a.tasks, lang)
        steps.append(_t("today_alert", lang, name=tr(kb.targets[a.target]["names"], lang), task=tasks[0] if tasks else ""))
        if len(seen) == 3:
            break
    v = _weather_view(db, kb, farm, lang)
    if v:
        for adv in sorted(v["advisories"], key=lambda x: x["severity"] != "warning")[:2]:
            steps.append(adv["title"])
    due = db.scalars(select(FollowUp).join(Problem, FollowUp.problem_id == Problem.id)
                     .where(Problem.farm_id == farm.id, FollowUp.response.is_(None), FollowUp.due_on <= today)).first()
    if due:
        p = db.get(Problem, due.problem_id)
        name = tr(kb.targets[p.target]["names"], lang) if p and p.target in kb.targets else _crop(kb, farm, lang)
        steps.append(_t("today_followup", lang, name=name))
    intro = _t("today_intro", lang, crop=_crop(kb, farm, lang), stage=kb.stage_name(farm.crop, stage, lang), das=das)
    if not steps:
        return {"text": f"{intro} {_t('today_calm', lang)}", "steps": [], "go": _go([GO["weather"]], lang)}
    return {"text": intro, "steps": steps, "go": _go([GO["alerts"], GO["weather"]], lang)}


def _weather(db: Session, kb: KB, farm: Farm, lang: str) -> dict:
    v = _weather_view(db, kb, farm, lang)
    if v is None:
        return {"text": _t("no_weather", lang), "steps": [], "go": _go([GO["weather"]], lang)}
    cur = v["current"]
    parts = [_t("weather_line", lang, temp=round(cur["temp"]), rh=cur["rh"], prob=cur.get("prob_3h") or 0)]
    today = agroweather.now_ist().date()
    nxt = [d for d in v["daily"] if date.fromisoformat(d["on"]) > today][:3]
    mm = round(sum(d.get("rain") or 0 for d in nxt))
    parts.append(_t("weather_days", lang, mm=mm) if mm >= 2 else _t("weather_dry", lang))
    steps = [a["title"] for a in sorted(v["advisories"], key=lambda x: x["severity"] != "warning")[:3]]
    return {"text": " ".join(parts), "steps": steps, "go": _go([GO["weather"]], lang)}


def _when(iso: str, lang: str) -> str:
    t = datetime.fromisoformat(iso)
    today = agroweather.now_ist().date()
    day = _t("today", lang) if t.date() == today else _t("tomorrow", lang) if t.date() == today + timedelta(days=1) \
        else local_date(t.date(), lang, year=False)
    return f"{day} {t:%H:%M}"


def _spray(db: Session, kb: KB, farm: Farm, lang: str) -> dict:
    v = _weather_view(db, kb, farm, lang)
    if v is None:
        return {"text": _t("no_weather", lang), "steps": [], "go": _go([GO["weather"]], lang)}
    sp = v["spray"]
    status = (sp.get("now") or {}).get("status", "avoid")
    why = sp.get("reasons_text") or ""
    text = _t("spray_good", lang) if status == "good" else _t(f"spray_{status}", lang, why=why)
    steps = []
    if status != "good":
        w = sp.get("windows") or []
        steps.append(_t("spray_next", lang, when=f"{_when(w[0]['start'], lang)}–{datetime.fromisoformat(w[0]['end']):%H:%M}")
                     if w else _t("spray_none", lang))
    steps.append(_t("spray_first", lang))
    return {"text": text, "steps": steps, "go": _go([GO["weather"], GO["spray"]], lang)}


def _water(db: Session, kb: KB, farm: Farm, lang: str) -> dict:
    v = _weather_view(db, kb, farm, lang)
    if v is None:
        return {"text": _t("no_weather", lang), "steps": [], "go": _go([GO["weather"]], lang)}
    w = v.get("water") or {}
    if not w.get("available"):
        return {"text": _t("water_unknown", lang), "steps": [], "go": _go([GO["weather"]], lang)}
    verdict = w["verdict"]
    text = {
        "irrigate": lambda: _t("water_irrigate", lang, crop=_crop(kb, farm, lang), etc=round(w["etc_week"]),
                               rain=round(w["eff_rain_week"])),
        "hold_rain": lambda: _t("water_hold_rain", lang, mm=round(w["next3_rain"])),
        "ok": lambda: _t("water_ok", lang),
        "stop_stage": lambda: _t("water_stop_stage", lang),
    }[verdict]()
    return {"text": text, "steps": [], "go": _go([GO["weather"]], lang)}


def _risks(db: Session, kb: KB, farm: Farm, lang: str) -> dict:
    today = _today_ist()
    scores = services.risk_scores(db, kb, farm, today, services.weather_for(db, farm))
    if not scores:
        return {"text": _t("risks_none", lang), "steps": [], "go": _go([GO["alerts"]], lang)}
    steps = [f"{tr(kb.targets[s.target]['names'], lang)} — {_t('level_' + s.level, lang)}" for s in scores[:4]]
    return {"text": _t("risks_intro", lang), "steps": steps, "go": _go([GO["alerts"], GO["weather"]], lang)}


def _cases(db: Session, kb: KB, farm: Farm, lang: str) -> dict:
    problems = db.scalars(select(Problem).where(Problem.farm_id == farm.id).order_by(Problem.id.desc())).all()[:3]
    if not problems:
        return {"text": _t("cases_none", lang), "steps": [], "go": _go([GO["scan"]], lang)}
    steps = []
    for p in services.problem_views(db, kb, problems, lang):
        name = p["name"] or _t("case_unknown", lang)
        if p["expert"]:
            line = _t(f"case_{p['expert']['verdict']}", lang, name=name, expert=p["expert"]["expert_name"])
            if p["expert"].get("notes"):
                line += " " + _t("case_note", lang, note=p["expert"]["notes"])
        elif p["case"] and p["case"]["status"] == "open":
            line = _t("case_waiting", lang, name=name, pos=p["case"]["queue_position"], eta=p["case"]["eta_minutes"])
        elif p["status"] == "resolved":
            line = _t("case_resolved", lang, name=name)
        elif p["advisory"]:
            line = _t("case_advised", lang, name=name)
        else:
            line = _t("case_open", lang, name=name)
        steps.append(line)
    return {"text": _t("cases_intro", lang), "steps": steps, "go": _go([GO["history"]], lang)}


# --------------------------------------------------------------------------
# The farmer's own details
#
# Krishi is a personal assistant after sign-in, which makes the boundary the
# important part: everything below is built from `user` and `farms`, and the
# caller resolves those from the session cookie alone (routers/krishi.py). No
# id from the request body reaches this code, so one farmer's question cannot
# read another farmer's rows — there is no query here that could.
# --------------------------------------------------------------------------

def facts(db: Session, kb: KB, user, farms: list[Farm], lang: str) -> str:
    """Everything Krishi may say about this farmer, as plain lines. Nothing
    here is generated: each line is a column of their own rows."""
    if user is None:
        return ""
    out: list[str] = []
    prof = db.get(FarmerProfile, user.id)
    place = ", ".join(x for x in (prof.village, prof.taluka, prof.district, prof.state) if x) if prof else ""
    out.append(f"Farmer's name: {user.name}")
    if user.email:
        out.append(f"Sign-in email: {user.email}")
    if user.phone:
        out.append(f"Phone on the account: {user.phone}")
    if place:
        out.append(f"Home village/district: {place}")
    if prof and prof.total_land_acres:
        out.append(f"Total land: {prof.total_land_acres} acres")
    out.append(f"App language: {lang}")
    out.append(f"Number of fields registered: {len(farms)}")

    today = _today_ist()
    for i, f in enumerate(farms, 1):
        stage, das = kb.stage_for(f.crop, f.sowing_date, today)
        where = ", ".join(x for x in (f.village, f.taluka, f.district, f.state) if x)
        line = (f"Field {i}: {tr(kb.crops[f.crop]['names'], 'en')}"
                f"{f' variety {f.variety}' if f.variety else ''}, {f.area_acres} acres, at {where}. "
                f"Sown {f.sowing_date.strftime('%d %b %Y')}, {das} days ago, now at the "
                f"{kb.stage_name(f.crop, stage, 'en')} stage.")
        if f.irrigation:
            line += f" Watered by: {f.irrigation}."
        if f.soil_ph:
            line += f" Soil pH {f.soil_ph}."
        line += (" Photo diagnosis is available for this crop."
                 if kb.crops[f.crop]["photo_diagnosis"] else
                 " Photo diagnosis is not available for this crop yet; it still gets risk alerts and expert help.")
        out.append(line)
        for p in services.problem_views(db, kb, db.scalars(
                select(Problem).where(Problem.farm_id == f.id).order_by(Problem.id.desc())).all()[:3], "en"):
            name = p["name"] or "an unidentified problem"
            if p["expert"]:
                out.append(f"  Field {i} problem: {name} — the expert {p['expert']['expert_name']} "
                           f"{p['expert']['verdict']} it.")
            elif p["case"] and p["case"]["status"] == "open":
                out.append(f"  Field {i} problem: {name} — waiting for an expert.")
            else:
                out.append(f"  Field {i} problem: {name} — {p['status']}.")
    return "\n".join(out)


NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _values(text: str) -> set[float]:
    out = set()
    for n in NUMBER.findall(text or ""):
        try:
            out.add(float(n.replace(",", ".")))
        except ValueError:
            continue
    return out


def grounded(reply: str, source: str) -> bool:
    """True when every number in `reply` is one of the farmer's own.

    A model asked to answer from facts mostly does, and occasionally rounds an
    acre or invents a day. Numbers are what a farmer acts on, so any number not
    in their own rows sends the answer back and the templated one is shown.

    Compared by value, not by spelling: "3 acres" is a fair way to say "3.0
    acres" and "6 July" to say "06 Jul", and rejecting those would throw away
    good answers. An invented 5 acres still has no 5 to match."""
    have = _values(source)
    return _values(reply) <= have


def _personal(db: Session, kb: KB, user, farms: list[Farm], question: str, lang: str, screen: str | None) -> dict | None:
    """Answer a question about the farmer's own field from their own rows."""
    if user is None or not nim.enabled():
        return None
    sheet = facts(db, kb, user, farms, lang)
    if not sheet:
        return None
    said = nim.say(question, sheet, lang)
    if said is None:
        return None
    text, steps = said
    if not grounded(" ".join([text, *steps]), sheet):
        return None
    return {"topic": PERSONAL, "score": 1.0, "text": text, "steps": steps, "go": _go([GO["home"]], lang),
            "suggestions": suggestions(screen, lang)}


def _fused_rank(idx: Index, text: str, lang: str, screen: str | None) -> list[tuple[str, float]]:
    """Topics scored on the farmer's own words plus their English translation."""
    key = f"krishi:en:{lang}:{' '.join(text.lower().split())[:200]}"
    en = cache.get_json(key)
    if en is None:
        try:
            en = voice.translate(text, lang, "en") or ""
        except Exception:  # noqa: BLE001 — no translation: the native score stands
            return []
        cache.set_json(key, en, 7 * 24 * 3600)
    total: Counter = Counter()
    for tid, sc in idx.rank(text, screen) + idx.rank(en, screen):
        total[tid] += sc
    return total.most_common()


def _route(text: str, idx: Index) -> str | None:
    """What the farmer meant, read by the model, as one of our own topic ids."""
    topics = [(tid, " / ".join(t["ask"]["en"][:3]) + " | " + ", ".join(t.get("keys", [])[:10]))
              for tid, t in idx.topics.items()]
    topics.append((PERSONAL, "what crops do I grow / where is my field / how big is my land / "
                             "when did I sow / what is my name, village, phone | my, mera, majha, apna"))
    return nim.route(text, topics)


def _farm_line(db: Session, kb: KB, farm: Farm, lang: str) -> dict:
    stage, das = kb.stage_for(farm.crop, farm.sowing_date, _today_ist())
    place = ", ".join(x for x in (farm.village, farm.district) if x)
    crop = _crop(kb, farm, lang) + (f" ({farm.variety})" if farm.variety else "")
    text = _t("farm_line", lang, crop=crop,
              place=place, sown=local_date(farm.sowing_date, lang), das=das,
              stage=kb.stage_name(farm.crop, stage, lang), area=farm.area_acres)
    return {"text": text, "steps": [], "go": _go([GO["home"]], lang)}
