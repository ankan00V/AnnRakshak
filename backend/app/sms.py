"""SMS: the channel that reaches every farmer, smartphone or not.

A sign-in code for a farmer's mobile number, and the three moments worth an
interruption — a weather warning, the expert's answer, and the day-four
question about whether the treatment worked — go by SMS once a provider is
configured. Replies come back through /api/sms/inbound (routers/sms.py), so a
farmer with a basic phone can answer "3" and reach an expert again.

Delivery backends (config.SMS_BACKEND), like mailer.py's:
  off     nothing is sent; codes go by email and alerts by app, push and email
  outbox  each message is written to DATA_DIR/sms-outbox — a laptop; nothing leaves it
  msg91   MSG91 Flow API, with a DLT template id per kind of message (India)
  twilio  Twilio Messages API

Rules that hold whichever backend is in use:
- send() never raises and returns (status, error), as mailer.send does;
- a full number never reaches a log line or the database (mask());
- one number gets at most SMS_MAX_PER_NUMBER_PER_HOUR messages of any kind;
- a message is trimmed to SMS_MAX_PARTS segments, counting the way a handset
  does: 160 Latin characters, or 70 once there is a single Indian letter in it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import math
import re
import unicodedata
import uuid
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app import cache, config
from app.kb import tr
from app.models import SmsLog

log = logging.getLogger("annrakshak.sms")

KINDS = ("otp", "warning", "verdict", "followup", "reply")
ALERT_KINDS = ("warning", "verdict", "followup")
"""What the per-field daily cap counts. A sign-in code is asked for by the
person reading it, and a reply answers a message they sent us."""


# --------------------------------------------------------------------------
# What the farmer reads
# --------------------------------------------------------------------------

TEXT = {
    # A sign-in code: the code, how long it lasts, and nothing else. No link:
    # a link in a code message is what a phishing message looks like.
    "otp": {
        "en": "{code} is your AnnRakshak code. It works for {mins} minutes.",
        "hi": "{code} आपका AnnRakshak कोड है। यह {mins} मिनट तक चलेगा।",
        "mr": "{code} हा तुमचा AnnRakshak कोड आहे. तो {mins} मिनिटे चालेल.",
        "bn": "{code} আপনার AnnRakshak কোড। এটি {mins} মিনিট কাজ করবে।",
        "ta": "{code} உங்கள் AnnRakshak குறியீடு. இது {mins} நிமிடங்கள் செல்லும்.",
        "te": "{code} మీ AnnRakshak కోడ్. ఇది {mins} నిమిషాలు పనిచేస్తుంది.",
        "kn": "{code} ನಿಮ್ಮ AnnRakshak ಕೋಡ್. ಇದು {mins} ನಿಮಿಷ ಮಾನ್ಯ.",
        "ml": "{code} നിങ്ങളുടെ AnnRakshak കോഡ് ആണ്. ഇത് {mins} മിനിറ്റ് സാധുവാണ്.",
        "gu": "{code} તમારો AnnRakshak કોડ છે. તે {mins} મિનિટ ચાલશે.",
        "pa": "{code} ਤੁਹਾਡਾ AnnRakshak ਕੋਡ ਹੈ। ਇਹ {mins} ਮਿੰਟ ਚੱਲੇਗਾ।",
    },
    # How to answer the follow-up question by SMS.
    "options": {
        "en": "Reply 1 if better, 2 if the same, 3 if worse.",
        "hi": "बेहतर हो तो 1, वैसा ही हो तो 2, बिगड़ा हो तो 3 भेजें।",
        "mr": "बरे असेल तर 1, तसेच असेल तर 2, बिघडले असेल तर 3 पाठवा.",
        "bn": "ভালো হলে 1, একই থাকলে 2, খারাপ হলে 3 পাঠান।",
        "ta": "நன்றாக இருந்தால் 1, அப்படியே இருந்தால் 2, மோசமானால் 3 அனுப்புங்கள்.",
        "te": "మెరుగైతే 1, అలాగే ఉంటే 2, దిగజారితే 3 పంపండి.",
        "kn": "ಸುಧಾರಿಸಿದ್ದರೆ 1, ಹಾಗೆಯೇ ಇದ್ದರೆ 2, ಹದಗೆಟ್ಟಿದ್ದರೆ 3 ಕಳುಹಿಸಿ.",
        "ml": "ഭേദമായെങ്കിൽ 1, അതുപോലെയെങ്കിൽ 2, വഷളായെങ്കിൽ 3 അയയ്ക്കുക.",
        "gu": "સારું હોય તો 1, એવું જ હોય તો 2, બગડ્યું હોય તો 3 મોકલો.",
        "pa": "ਬਿਹਤਰ ਹੋਵੇ ਤਾਂ 1, ਉਵੇਂ ਹੀ ਹੋਵੇ ਤਾਂ 2, ਵਿਗੜ ਗਈ ਹੋਵੇ ਤਾਂ 3 ਭੇਜੋ।",
    },
    # When nobody is listening for replies: never invite one.
    "in_app": {
        "en": "Tell us in the app:", "hi": "ऐप में बताइए:", "mr": "ॲपमध्ये सांगा:",
        "bn": "অ্যাপে জানান:", "ta": "செயலியில் சொல்லுங்கள்:", "te": "యాప్‌లో చెప్పండి:",
        "kn": "ಆ್ಯಪ್‌ನಲ್ಲಿ ತಿಳಿಸಿ:", "ml": "ആപ്പിൽ അറിയിക്കുക:", "gu": "ઍપમાં જણાવો:", "pa": "ਐਪ ਵਿੱਚ ਦੱਸੋ:",
    },
    "thanks_improved": {
        "en": "Thank you. Glad your crop is better.",
        "hi": "धन्यवाद। अच्छा है कि फसल बेहतर है।",
        "mr": "धन्यवाद. पीक बरे आहे हे ऐकून आनंद झाला.",
        "bn": "ধন্যবাদ। ফসল ভালো আছে জেনে খুশি হলাম।",
        "ta": "நன்றி. பயிர் நன்றாக இருப்பது மகிழ்ச்சி.",
        "te": "ధన్యవాదాలు. పంట మెరుగ్గా ఉండటం సంతోషం.",
        "kn": "ಧನ್ಯವಾದ. ಬೆಳೆ ಸುಧಾರಿಸಿರುವುದು ಸಂತೋಷ.",
        "ml": "നന്ദി. വിള ഭേദമായതിൽ സന്തോഷം.",
        "gu": "આભાર. પાક સારો છે એ જાણી આનંદ થયો.",
        "pa": "ਧੰਨਵਾਦ। ਖੁਸ਼ੀ ਹੈ ਕਿ ਫ਼ਸਲ ਬਿਹਤਰ ਹੈ।",
    },
    "thanks_no_change": {
        "en": "Thank you. We will ask again in {days} days.",
        "hi": "धन्यवाद। हम {days} दिन बाद फिर पूछेंगे।",
        "mr": "धन्यवाद. आम्ही {days} दिवसांनी पुन्हा विचारू.",
        "bn": "ধন্যবাদ। আমরা {days} দিন পরে আবার জিজ্ঞেস করব।",
        "ta": "நன்றி. {days} நாட்களில் மீண்டும் கேட்போம்.",
        "te": "ధన్యవాదాలు. {days} రోజుల తర్వాత మళ్లీ అడుగుతాం.",
        "kn": "ಧನ್ಯವಾದ. {days} ದಿನಗಳ ನಂತರ ಮತ್ತೆ ಕೇಳುತ್ತೇವೆ.",
        "ml": "നന്ദി. {days} ദിവസത്തിനു ശേഷം വീണ്ടും ചോദിക്കാം.",
        "gu": "આભાર. અમે {days} દિવસ પછી ફરી પૂછીશું.",
        "pa": "ਧੰਨਵਾਦ। ਅਸੀਂ {days} ਦਿਨਾਂ ਬਾਅਦ ਫਿਰ ਪੁੱਛਾਂਗੇ।",
    },
    "thanks_got_worse": {
        "en": "Thank you. An expert will look at your crop again.",
        "hi": "धन्यवाद। एक विशेषज्ञ आपकी फसल फिर से देखेंगे।",
        "mr": "धन्यवाद. तज्ज्ञ तुमचे पीक पुन्हा पाहतील.",
        "bn": "ধন্যবাদ। একজন বিশেষজ্ঞ আবার আপনার ফসল দেখবেন।",
        "ta": "நன்றி. ஒரு நிபுணர் உங்கள் பயிரை மீண்டும் பார்ப்பார்.",
        "te": "ధన్యవాదాలు. ఒక నిపుణుడు మీ పంటను మళ్లీ పరిశీలిస్తారు.",
        "kn": "ಧನ್ಯವಾದ. ತಜ್ಞರು ನಿಮ್ಮ ಬೆಳೆಯನ್ನು ಮತ್ತೆ ನೋಡುತ್ತಾರೆ.",
        "ml": "നന്ദി. ഒരു വിദഗ്ധൻ നിങ്ങളുടെ വിള വീണ്ടും പരിശോധിക്കും.",
        "gu": "આભાર. નિષ્ણાત તમારો પાક ફરી જોશે.",
        "pa": "ਧੰਨਵਾਦ। ਮਾਹਰ ਤੁਹਾਡੀ ਫ਼ਸਲ ਨੂੰ ਦੁਬਾਰਾ ਵੇਖਣਗੇ।",
    },
    # STOP and START: the only switch a farmer without the app can reach.
    "stopped": {
        "en": "You will get no more alerts by SMS. Send START to turn them on again.",
        "hi": "अब आपको SMS से अलर्ट नहीं आएँगे। फिर से चालू करने के लिए START भेजें।",
        "mr": "आता तुम्हाला SMS ने सूचना येणार नाहीत. पुन्हा सुरू करण्यासाठी START पाठवा.",
        "bn": "আপনি আর SMS-এ সতর্কবার্তা পাবেন না। আবার চালু করতে START পাঠান।",
        "ta": "இனி SMS மூலம் எச்சரிக்கைகள் வராது. மீண்டும் தொடங்க START அனுப்புங்கள்.",
        "te": "ఇకపై SMS ద్వారా హెచ్చరికలు రావు. మళ్లీ ప్రారంభించడానికి START పంపండి.",
        "kn": "ಇನ್ನು SMS ಮೂಲಕ ಎಚ್ಚರಿಕೆಗಳು ಬರುವುದಿಲ್ಲ. ಮತ್ತೆ ಆರಂಭಿಸಲು START ಕಳುಹಿಸಿ.",
        "ml": "ഇനി SMS വഴി മുന്നറിയിപ്പുകൾ വരില്ല. വീണ്ടും തുടങ്ങാൻ START അയയ്ക്കുക.",
        "gu": "હવે તમને SMS થી ચેતવણી નહીં આવે. ફરી શરૂ કરવા START મોકલો.",
        "pa": "ਹੁਣ ਤੁਹਾਨੂੰ SMS ਰਾਹੀਂ ਚੇਤਾਵਨੀਆਂ ਨਹੀਂ ਆਉਣਗੀਆਂ। ਦੁਬਾਰਾ ਚਾਲੂ ਕਰਨ ਲਈ START ਭੇਜੋ।",
    },
    "started": {
        "en": "Alerts by SMS are on again. Send STOP to turn them off.",
        "hi": "SMS से अलर्ट फिर चालू हैं। बंद करने के लिए STOP भेजें।",
        "mr": "SMS ने सूचना पुन्हा सुरू झाल्या. बंद करण्यासाठी STOP पाठवा.",
        "bn": "SMS-এ সতর্কবার্তা আবার চালু হয়েছে। বন্ধ করতে STOP পাঠান।",
        "ta": "SMS எச்சரிக்கைகள் மீண்டும் தொடங்கின. நிறுத்த STOP அனுப்புங்கள்.",
        "te": "SMS హెచ్చరికలు మళ్లీ మొదలయ్యాయి. ఆపడానికి STOP పంపండి.",
        "kn": "SMS ಎಚ್ಚರಿಕೆಗಳು ಮತ್ತೆ ಆರಂಭವಾಗಿವೆ. ನಿಲ್ಲಿಸಲು STOP ಕಳುಹಿಸಿ.",
        "ml": "SMS മുന്നറിയിപ്പുകൾ വീണ്ടും തുടങ്ങി. നിർത്താൻ STOP അയയ്ക്കുക.",
        "gu": "SMS થી ચેતવણી ફરી શરૂ થઈ છે. બંધ કરવા STOP મોકલો.",
        "pa": "SMS ਰਾਹੀਂ ਚੇਤਾਵਨੀਆਂ ਦੁਬਾਰਾ ਚਾਲੂ ਹਨ। ਬੰਦ ਕਰਨ ਲਈ STOP ਭੇਜੋ।",
    },
    "nothing_pending": {
        "en": "Thank you. There is no question waiting for you now.",
        "hi": "धन्यवाद। अभी आपसे कोई सवाल बाकी नहीं है।",
        "mr": "धन्यवाद. सध्या तुमच्यासाठी कोणताही प्रश्न बाकी नाही.",
        "bn": "ধন্যবাদ। এখন আপনার জন্য কোনো প্রশ্ন বাকি নেই।",
        "ta": "நன்றி. இப்போது உங்களுக்கு எந்தக் கேள்வியும் நிலுவையில் இல்லை.",
        "te": "ధన్యవాదాలు. ప్రస్తుతం మీకు ఏ ప్రశ్నా పెండింగ్‌లో లేదు.",
        "kn": "ಧನ್ಯವಾದ. ಈಗ ನಿಮಗೆ ಯಾವುದೇ ಪ್ರಶ್ನೆ ಬಾಕಿ ಇಲ್ಲ.",
        "ml": "നന്ദി. ഇപ്പോൾ നിങ്ങൾക്കായി ചോദ്യങ്ങളൊന്നും ബാക്കിയില്ല.",
        "gu": "આભાર. હમણાં તમારા માટે કોઈ પ્રશ્ન બાકી નથી.",
        "pa": "ਧੰਨਵਾਦ। ਇਸ ਵੇਲੇ ਤੁਹਾਡੇ ਲਈ ਕੋਈ ਸਵਾਲ ਬਾਕੀ ਨਹੀਂ।",
    },
}


def say(key: str, lang: str, **kw) -> str:
    s = tr(TEXT[key], lang)
    return s.format(**kw) if kw else s


def otp_text(code: str, mins: int, lang: str) -> str:
    return say("otp", lang, code=code, mins=mins)


# --------------------------------------------------------------------------
# Length, counted the way the handset counts it
# --------------------------------------------------------------------------

GSM_BASIC = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
GSM_EXTENDED = set("^{}\\[~]|€")
"""The GSM 03.38 alphabet. One character outside both sets — a single Devanagari
letter, an em dash, a degree sign — turns the whole message into UCS-2, and a
segment shrinks from 160 characters to 70."""

_PLAIN = {"—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "°C": " C", "°": "", "…": "...",
          " ": " "}


def plain(text: str) -> str:
    """Typography that costs a segment and says nothing an SMS needs."""
    for a, b in _PLAIN.items():
        text = text.replace(a, b)
    return re.sub(r"[ \t]+", " ", text).strip()


def is_gsm(text: str) -> bool:
    return all(c in GSM_BASIC or c in GSM_EXTENDED for c in text)


def segments(text: str) -> int:
    if is_gsm(text):
        n = sum(2 if c in GSM_EXTENDED else 1 for c in text)
        return 1 if n <= 160 else math.ceil(n / 153)
    n = sum(2 if ord(c) > 0xFFFF else 1 for c in text)
    return 1 if n <= 70 else math.ceil(n / 67)


def fit(text: str, link: str | None = None, parts: int | None = None) -> tuple[str, str]:
    """(the text, trimmed; the whole message) within `parts` segments.

    The link is never cut — a broken link is worse than none — so the words
    give way, at a word boundary where there is one, and say they were cut."""
    parts = parts or config.SMS_MAX_PARTS
    text = plain(text)
    tail = f" {link}" if link else ""
    if segments(text + tail) <= parts:
        return text, text + tail
    dots = "..." if is_gsm(text + tail) else "…"
    cut = len(text)
    while cut > 0:
        cut -= 1
        head = text[:cut]
        space = head.rfind(" ")
        if space > cut * 0.6:
            head = head[:space]
        head = head.rstrip(" ,.;:-") + dots
        if segments(head + tail) <= parts:
            return head, head + tail
    return "", link or ""


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------

def mask(number: str | None) -> str:
    """+91 ••••••1234. The only form a number takes in a log or a table."""
    digits = re.sub(r"\D", "", number or "")
    if len(digits) < 4:
        return "••••"
    return f"+{digits[:-10]} ••••••{digits[-4:]}" if len(digits) > 10 else f"••••••{digits[-4:]}"


# --------------------------------------------------------------------------
# Is it on
# --------------------------------------------------------------------------

def enabled(kind: str = "otp") -> bool:
    """Whether a message of this kind can be sent right now.

    Production refuses to start half-configured (config.sms_problems); a
    laptop may be, and then the kinds without a template simply do not go."""
    backend = config.SMS_BACKEND
    if backend == "outbox":
        return True
    if backend == "msg91":
        return bool(config.MSG91_AUTH_KEY and config.SMS_SENDER_ID and config.MSG91_TEMPLATES.get(kind))
    if backend == "twilio":
        return bool(config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_FROM)
    return False


def inbound_ready() -> bool:
    """Whether a reply would be read. The follow-up message invites one only
    then: asking a farmer to text "3" into a number nobody listens on is
    worse than not asking."""
    if not enabled("reply"):
        return False
    return bool(config.SMS_INBOUND_SECRET or (config.SMS_BACKEND == "twilio" and config.TWILIO_AUTH_TOKEN))


# --------------------------------------------------------------------------
# Sending
# --------------------------------------------------------------------------

def _key(number: str) -> str:
    """The number as a rate-limit key: a hash, because Redis keys are listed
    by anyone who can run KEYS, and a list of farmers' phone numbers is
    exactly what this module never writes down."""
    return hashlib.sha256(re.sub(r"\D", "", number or "").encode()).hexdigest()[:20]


def _scrub(s: str) -> str:
    """A provider's error text, without anything that looks like a number in it."""
    return re.sub(r"\d{6,}", "…", s or "")[:120]


def _outbox(to: str, text: str, kind: str, variables: dict) -> tuple[str, str | None]:
    folder = config.DATA_DIR / "sms-outbox"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{datetime.now():%Y%m%d-%H%M%S}-{kind}-{uuid.uuid4().hex[:6]}.txt"
    head = [f"To: {to}", f"Kind: {kind}", f"Segments: {segments(text)}"]
    head += [f"Var-{k}: {v}" for k, v in variables.items()]
    (folder / name).write_text("\n".join(head) + "\n\n" + text + "\n", encoding="utf-8")
    return "outbox", None


def _msg91(to: str, text: str, kind: str, variables: dict) -> tuple[str, str | None]:
    recipient = {"mobiles": re.sub(r"\D", "", to)} | {k: str(v) for k, v in variables.items()}
    payload = {"template_id": config.MSG91_TEMPLATES[kind], "sender": config.SMS_SENDER_ID,
               "short_url": "0", "recipients": [recipient]}
    r = httpx.post(config.MSG91_FLOW_URL, json=payload, timeout=config.SMS_TIMEOUT_S,
                   headers={"authkey": config.MSG91_AUTH_KEY, "accept": "application/json"})
    if r.status_code >= 400:
        return "failed", f"msg91 HTTP {r.status_code}"
    try:
        body = r.json()
    except ValueError:
        return "failed", "msg91 answered with something that is not JSON"
    if str(body.get("type", "")).lower() == "error":
        return "failed", f"msg91: {_scrub(str(body.get('message', '')))}"
    return "sent", None


def _twilio(to: str, text: str) -> tuple[str, str | None]:
    sid = config.TWILIO_ACCOUNT_SID
    data = {"To": to, "Body": text}
    data["MessagingServiceSid" if config.TWILIO_FROM.startswith("MG") else "From"] = config.TWILIO_FROM
    r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=data,
                   auth=(sid, config.TWILIO_AUTH_TOKEN), timeout=config.SMS_TIMEOUT_S)
    if r.status_code >= 400:
        try:
            code = r.json().get("code")
        except ValueError:
            code = None
        return "failed", f"twilio HTTP {r.status_code}{f' code {code}' if code else ''}"
    return "sent", None


def send(to: str, text: str, *, kind: str, variables: dict | None = None) -> tuple[str, str | None]:
    """Returns (status, error): ('sent'|'outbox', None), ('limited', why) or
    ('failed', why). Never raises: a provider that is down must not turn a
    sign-in or a verdict into a 500.

    `text` is the whole message as the farmer reads it. `variables` are what a
    DLT template is filled with (config.MSG91_TEMPLATES); without them the
    template gets the whole text as `text`."""
    if kind not in KINDS:
        return "failed", f"unknown kind {kind!r}"
    if not enabled(kind):
        return "failed", "sms is not configured for this kind of message"
    if cache.hit(f"sms:to:{_key(to)}", 3600) > config.SMS_MAX_PER_NUMBER_PER_HOUR:
        log.warning("sms %s to %s held back: hourly limit for this number", kind, mask(to))
        return "limited", "too many messages to this number this hour"
    variables = {"text": text} | (variables or {})
    try:
        if config.SMS_BACKEND == "outbox":
            status, err = _outbox(to, text, kind, variables)
        elif config.SMS_BACKEND == "msg91":
            status, err = _msg91(to, text, kind, variables)
        else:
            status, err = _twilio(to, text)
    except (httpx.HTTPError, OSError) as e:
        status, err = "failed", type(e).__name__
    log.info("sms %s to %s: %s%s", kind, mask(to), status, f" ({err})" if err else "")
    return status, err


def record(db: Session, *, number: str, direction: str, kind: str, status: str, farm_id: int | None = None,
           ref: str | None = None, delivered: bool = False, body: str | None = None,
           error: str | None = None) -> SmsLog:
    """One row in sms_log. `delivered` stamps the dedupe key, so that this
    message is never sent again for the same field and moment."""
    row = SmsLog(farm_id=farm_id, direction=direction, kind=kind, number=mask(number),
                 ref=(ref or None) and ref[:80], dedupe_key=(ref[:80] if delivered and ref else None),
                 body=(body or None) and body[:400], status=status, error=(error or None) and error[:200],
                 at=datetime.now())
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------
# Replies
# --------------------------------------------------------------------------

REPLY_WORDS = {
    "improved": [
        "better", "improved", "good", "recovered", "behtar", "accha", "achha", "acha",
        "बेहतर", "अच्छा", "अच्छी", "सुधरा", "सुधरी",
        "बरे", "बरं", "चांगले", "चांगलं", "सुधारले",
        "ভালো", "ভাল",
        "நன்று", "நன்றாக", "நல்லது",
        "మెరుగు", "మెరుగైంది", "బాగుంది",
        "ಉತ್ತಮ", "ಸುಧಾರಿಸಿದೆ", "ಚೆನ್ನಾಗಿದೆ",
        "ഭേദം", "ഭേദമായി", "നല്ലത്",
        "સારું", "સારો", "સુધર્યું",
        "ਬਿਹਤਰ", "ਚੰਗੀ", "ਚੰਗਾ",
    ],
    "no_change": [
        "same", "no change", "unchanged", "waisa", "waise", "vaisa",
        "वैसा ही", "वैसी ही", "वैसे ही", "वैसा", "वही", "समान",
        "तसेच", "तसंच", "सारखे", "तेच",
        "একই", "একই রকম",
        "அதே", "அப்படியே",
        "అలాగే", "అదే",
        "ಹಾಗೆಯೇ", "ಅದೇ",
        "അതുപോലെ", "മാറ്റമില്ല",
        "એવું જ", "એવુંજ", "સરખું",
        "ਉਵੇਂ ਹੀ", "ਉਹੀ",
    ],
    "got_worse": [
        "worse", "worst", "bad", "kharab", "bigda", "bigdi", "bura",
        "बिगड़ा", "बिगड़ी", "बिगडा", "खराब", "ख़राब", "बदतर",
        "बिघडले", "बिघडलं", "वाईट",
        "খারাপ",
        "மோசம்", "மோசமானது",
        "దిగజారింది", "అధ్వాన్నం", "చెడిపోయింది",
        "ಹದಗೆಟ್ಟಿದೆ", "ಕೆಟ್ಟದು", "ಕೆಟ್ಟಿದೆ",
        "മോശം", "വഷളായി",
        "ખરાબ", "બગડ્યું",
        "ਵਿਗੜ", "ਵਿਗੜੀ", "ਖ਼ਰਾਬ", "ਖਰਾਬ", "ਮਾੜਾ", "ਮਾੜੀ",
    ],
}
"""The words for the three answers, in every language the app speaks and the
way Hindi is typed on a phone keypad in Latin letters. Every language's words
are accepted from everyone: a Marathi farmer may well type in Hindi."""

NEGATIONS = {"not", "no", "nahi", "nahin", "nai", "नहीं", "नही", "ना", "नाही", "না", "নয়", "নেই", "இல்லை",
             "లేదు", "ಇಲ್ಲ", "ഇല്ല", "નથી", "ના", "ਨਹੀਂ", "ਨਹੀ"}
"""A word answer with one of these in it is not taken: "not better" read as
"better" would close a case on a crop that is dying. The farmer is sent the
options instead, and a digit is never in doubt."""

SWITCH_WORDS = {
    "off": {"stop", "unsubscribe", "band", "bandh", "बंद", "বন্ধ", "நிறுத்து", "ఆపు", "ನಿಲ್ಲಿಸಿ",
            "നിർത്തുക", "બંધ", "ਬੰਦ"},
    "on": {"start", "subscribe", "chalu", "चालू", "सुरू", "চালু", "தொடங்கு", "ప్రారంభం", "ಆರಂಭ",
           "തുടങ്ങുക", "ચાલુ", "ਚਾਲੂ"},
}
"""STOP and START, and the words a keypad in each script types for them. The
app's profile screen has the same switch; a farmer whose phone runs no app has
only this one, and an alert service nobody can turn off is not one they asked
for."""


def parse_switch(text: str) -> str | None:
    """'off' or 'on' when the whole message is a STOP or a START, else None.
    The whole message, so "stop the spray?" is a question, not an unsubscribe."""
    words = [w for w in _SPLIT.split(unicodedata.normalize("NFC", text or "").casefold()) if w]
    if not words or len(words) > 3:
        return None
    for value, names in SWITCH_WORDS.items():
        if all(w in names or w in ("sms", "alerts", "karo", "करो", "करें", "करा") for w in words) \
                and any(w in names for w in words):
            return value
    return None


DIGIT_ANSWER = {"1": "improved", "2": "no_change", "3": "got_worse"}
_SPLIT = re.compile(r"[\s,.;:!?।॥\"'()\[\]\-_/]+")


def _ascii_digits(s: str) -> str:
    """१, ১, ௧, ൧ ... are all a 1: a phone's keypad types the script it is set to."""
    return "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in s)


def parse_reply(text: str) -> tuple[str | None, str]:
    """(the follow-up answer or None, the rest of what they wrote).

    A leading 1, 2 or 3 decides, and whatever follows it is kept as the
    farmer's own words for the expert. Otherwise exactly one kind of answer
    word must appear, with no negation; anything else is unparsed, and the
    farmer is told the options rather than guessed at."""
    raw = unicodedata.normalize("NFC", (text or "").strip())
    norm = _ascii_digits(raw).casefold()
    m = re.match(r"^\s*([123])(?:[\s,.;:!?।)\-]+|$)", norm)
    if m:
        # The digit is one character in either spelling, so the farmer's own
        # words are whatever follows the first one, in their own script.
        rest = raw.lstrip()[1:].lstrip(" \t\r\n,.;:!?।)-")
        return DIGIT_ANSWER[m.group(1)], rest[:500]
    padded = " " + " ".join(t for t in _SPLIT.split(norm) if t) + " "
    hits = set()
    for answer, words in REPLY_WORDS.items():
        for w in sorted(words, key=len, reverse=True):
            if f" {w.casefold()} " in padded:
                hits.add(answer)
                padded = padded.replace(f" {w.casefold()} ", " ")
    if len(hits) != 1 or set(padded.split()) & NEGATIONS:
        return None, raw[:500]
    return hits.pop(), ""


def twilio_signature_ok(url: str, params: dict[str, str], signature: str) -> bool:
    """Twilio's X-Twilio-Signature: HMAC-SHA1 over the callback URL followed by
    every POST parameter, sorted by name, keyed with the account's auth token."""
    if not config.TWILIO_AUTH_TOKEN or not signature:
        return False
    data = url + "".join(k + params[k] for k in sorted(params))
    mac = hmac.new(config.TWILIO_AUTH_TOKEN.encode(), data.encode("utf-8"), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(mac).decode(), signature)
