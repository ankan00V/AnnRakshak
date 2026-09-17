"""Farm emails: an alert right away when a warning fires, and a daily summary of
the farm — weather now and ahead, soil pH and moisture, water balance, the
spray window, and the pests and diseases the weather is setting up for this
crop at this stage. Written in the farmer's language from the farm profile.

Delivery backends (config.EMAIL_BACKEND):
  smtp    any SMTP relay — Gmail (app password), Brevo, Amazon SES, Zoho ...
  outbox  writes .eml files to DATA_DIR/outbox — development and tests; nothing leaves the machine
Credentials come from .env and are never logged.
"""

from __future__ import annotations

import html
import re
import smtplib
import ssl
import uuid
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.kb import tr
from app.config import (
    DATA_DIR,
    EMAIL_BACKEND,
    EMAIL_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_SECURITY,
    SMTP_USER,
)

OUTBOX = DATA_DIR / "outbox"
LEAF, OCHRE, EMBER, CREAM, SOIL = "#1f3d2b", "#c8862d", "#b0472a", "#f7f3ec", "#2b1d12"
SEV_COLOR = {"warning": EMBER, "advice": OCHRE, "info": LEAF}
LEVEL_COLOR = {"high": EMBER, "medium": OCHRE, "low": "#6b6b6b"}

T = {
    "hello": {"en": "Namaste {name},", "hi": "नमस्ते {name},", "mr": "नमस्कार {name},"},
    "digest_subject": {"en": "Your {crop} farm today — {date}", "hi": "आज आपका {crop} खेत — {date}",
                       "mr": "आज तुमचे {crop} शेत — {date}"},
    "digest_intro": {
        "en": "Here is today's check for your {crop} in {district}: sown {sowing}, now {stage} (day {das}).",
        "hi": "{district} में आपकी {crop} की आज की जाँच: बुआई {sowing}, अभी {stage} (दिन {das})।",
        "mr": "{district} मधील तुमच्या {crop} ची आजची तपासणी: पेरणी {sowing}, सध्या {stage} (दिवस {das}).",
    },
    "alert_intro": {
        "en": "A weather warning for your {crop} farm in {district}:",
        "hi": "{district} में आपके {crop} खेत के लिए मौसम चेतावनी:",
        "mr": "{district} मधील तुमच्या {crop} शेतासाठी हवामान इशारा:",
    },
    "now": {"en": "Right now", "hi": "अभी", "mr": "आत्ता"},
    "next3": {"en": "Next 3 days", "hi": "अगले 3 दिन", "mr": "पुढील 3 दिवस"},
    "soil": {"en": "Soil", "hi": "मिट्टी", "mr": "माती"},
    "water": {"en": "Water", "hi": "पानी", "mr": "पाणी"},
    "spray": {"en": "Spraying", "hi": "छिड़काव", "mr": "फवारणी"},
    "todo": {"en": "What to do", "hi": "क्या करें", "mr": "काय करावे"},
    "risks": {"en": "Pests and diseases the weather favours", "hi": "मौसम के कारण बढ़ सकने वाले कीट व रोग",
              "mr": "हवामानामुळे वाढू शकणारे कीड व रोग"},
    "prevent": {"en": "Prevent it", "hi": "बचाव", "mr": "प्रतिबंध"},
    "avoid": {"en": "Don't", "hi": "न करें", "mr": "करू नका"},
    "all_calm": {"en": "No weather warnings for your farm today.", "hi": "आज आपके खेत के लिए कोई मौसम चेतावनी नहीं।",
                 "mr": "आज तुमच्या शेतासाठी हवामानाचा कोणताही इशारा नाही."},
    "temp": {"en": "Temperature", "hi": "तापमान", "mr": "तापमान"},
    "feels": {"en": "feels like", "hi": "महसूस", "mr": "जाणवते"},
    "rh": {"en": "Humidity", "hi": "नमी", "mr": "आर्द्रता"},
    "wind": {"en": "Wind", "hi": "हवा", "mr": "वारा"},
    "gust": {"en": "gusts", "hi": "झोंके", "mr": "झोत"},
    "rain_chance": {"en": "Rain chance (3 h)", "hi": "बारिश की संभावना (3 घं)", "mr": "पावसाची शक्यता (3 तास)"},
    "uv": {"en": "UV index", "hi": "UV सूचकांक", "mr": "UV निर्देशांक"},
    "ph": {"en": "pH", "hi": "pH (सामू)", "mr": "सामू (pH)"},
    "how_measured": {"en": "measured by your sensor", "hi": "आपके सेंसर से मापा", "mr": "तुमच्या सेन्सरने मोजलेले"},
    "how_card": {"en": "from your Soil Health Card", "hi": "आपके मृदा स्वास्थ्य कार्ड से", "mr": "तुमच्या मृदा आरोग्य पत्रिकेतून"},
    "how_estimated": {"en": "estimated from the soil map", "hi": "मिट्टी के नक्शे से अनुमान", "mr": "मातीच्या नकाशावरून अंदाज"},
    "moisture": {"en": "Moisture (modelled, 9–27 cm)", "hi": "नमी (मॉडल अनुमान, 9–27 सेमी)", "mr": "ओलावा (मॉडेल अंदाज, 9–27 सेंमी)"},
    "wb": {
        "en": "Crop used ≈ {etc} mm this week; effective rain ≈ {rain} mm; shortfall ≈ {deficit} mm.",
        "hi": "इस हफ़्ते फसल ने ≈ {etc} मिमी पानी लिया; उपयोगी बारिश ≈ {rain} मिमी; कमी ≈ {deficit} मिमी।",
        "mr": "या आठवड्यात पिकाने ≈ {etc} मिमी पाणी वापरले; उपयोगी पाऊस ≈ {rain} मिमी; तूट ≈ {deficit} मिमी.",
    },
    "wb_irrigate": {"en": "Irrigate if the soil is dry 5 cm down.", "hi": "5 सेमी नीचे मिट्टी सूखी हो तो सिंचाई करें।",
                    "mr": "5 सेंमी खाली माती कोरडी असल्यास पाणी द्या."},
    "wb_hold_rain": {"en": "Useful rain is forecast — hold irrigation.", "hi": "काम की बारिश का अनुमान है — सिंचाई रोकें।",
                     "mr": "उपयोगी पावसाचा अंदाज आहे — पाणी देणे थांबवा."},
    "wb_ok": {"en": "No irrigation needed now.", "hi": "अभी सिंचाई की ज़रूरत नहीं।", "mr": "सध्या पाणी देण्याची गरज नाही."},
    "wb_stop_stage": {"en": "The crop is maturing — irrigation is normally stopped now.",
                      "hi": "फसल पक रही है — अब आम तौर पर सिंचाई बंद की जाती है।",
                      "mr": "पीक पक्व होत आहे — आता साधारणपणे पाणी देणे थांबवले जाते."},
    "spray_best": {"en": "Best time to spray: {when}", "hi": "छिड़काव का अच्छा समय: {when}", "mr": "फवारणीची योग्य वेळ: {when}"},
    "spray_none": {"en": "No good spraying window in the next 48 hours.", "hi": "अगले 48 घंटे छिड़काव का अच्छा समय नहीं।",
                   "mr": "पुढील 48 तास फवारणीसाठी योग्य वेळ नाही."},
    "open_app": {"en": "Open AnnRakshak", "hi": "AnnRakshak खोलें", "mr": "AnnRakshak उघडा"},
    "why_this": {
        "en": "Based on your farm profile ({crop}, {district}) and live weather from {source}. Advice comes from the AnnRakshak knowledge base (IMD, FAO, ICAR sources); for any product dose, the printed label decides.",
        "hi": "आपके खेत की जानकारी ({crop}, {district}) और {source} के ताज़ा मौसम पर आधारित। सलाह AnnRakshak ज्ञान-आधार (IMD, FAO, ICAR स्रोत) से है; किसी भी दवा की मात्रा के लिए लेबल ही मान्य है।",
        "mr": "तुमच्या शेताची माहिती ({crop}, {district}) आणि {source} च्या ताज्या हवामानावर आधारित. सल्ला AnnRakshak ज्ञानभांडारातून (IMD, FAO, ICAR स्रोत); कोणत्याही औषधाच्या मात्रेसाठी लेबलच ग्राह्य.",
    },
    "unsubscribe": {"en": "Stop these emails", "hi": "ये ईमेल बंद करें", "mr": "हे ईमेल बंद करा"},
    "test_subject": {"en": "AnnRakshak: email alerts are on for {crop}", "hi": "AnnRakshak: {crop} के लिए ईमेल अलर्ट चालू",
                     "mr": "AnnRakshak: {crop} साठी ईमेल सूचना सुरू"},
    "test_body": {
        "en": "You will get weather warnings for your farm right away, and a short summary every morning at 6.",
        "hi": "आपके खेत के लिए मौसम चेतावनी तुरंत मिलेगी, और हर सुबह 6 बजे छोटा सारांश।",
        "mr": "तुमच्या शेतासाठी हवामान इशारे लगेच मिळतील, आणि दररोज सकाळी 6 वाजता छोटा सारांश.",
    },
    "otp_subject": {"en": "{code} is your AnnRakshak code", "hi": "{code} आपका AnnRakshak कोड है",
                    "mr": "{code} हा तुमचा AnnRakshak कोड आहे"},
    "otp_signup": {"en": "Use this code to finish creating your AnnRakshak account.",
                   "hi": "अपना AnnRakshak खाता बनाने के लिए यह कोड डालें।",
                   "mr": "तुमचे AnnRakshak खाते तयार करण्यासाठी हा कोड टाका."},
    "otp_login": {"en": "Use this code to sign in to AnnRakshak.", "hi": "AnnRakshak में साइन इन करने के लिए यह कोड डालें।",
                  "mr": "AnnRakshak मध्ये साइन इन करण्यासाठी हा कोड टाका."},
    "otp_expiry": {"en": "It works for {mins} minutes, once.", "hi": "यह {mins} मिनट तक, एक बार चलेगा।",
                   "mr": "तो {mins} मिनिटे, एकदाच चालेल."},
    "otp_warn": {"en": "Never share this code. AnnRakshak staff, KVK experts and officers will never ask for it. "
                       "If you did not ask for it, ignore this email.",
                 "hi": "यह कोड किसी को न बताएँ। AnnRakshak, KVK विशेषज्ञ या अधिकारी इसे कभी नहीं माँगेंगे। "
                       "अगर आपने यह नहीं माँगा, तो इस ईमेल को अनदेखा करें।",
                 "mr": "हा कोड कोणालाही सांगू नका. AnnRakshak, KVK तज्ज्ञ किंवा अधिकारी तो कधीही मागणार नाहीत. "
                       "तुम्ही तो मागितला नसेल तर हा ईमेल दुर्लक्षित करा."},
}


def t(key: str, lang: str, **kw) -> str:
    s = tr(T[key], lang)
    return s.format(**kw) if kw else s


def _e(s) -> str:
    return html.escape(str(s)) if s is not None else ""


# --------------------------------------------------------------------------
# HTML building blocks (inline styles: most mail clients strip <style>)
# --------------------------------------------------------------------------

def _shell(title: str, body: str, footer: str, preheader: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{_e(title)}</title></head>
<body style="margin:0;padding:0;background:{CREAM};font-family:'Noto Sans Devanagari',Inter,Arial,sans-serif;color:{SOIL}">
<span style="display:none;max-height:0;overflow:hidden;opacity:0">{_e(preheader)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM}"><tr><td align="center" style="padding:16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e6dfd3">
<tr><td style="background:{LEAF};color:{CREAM};padding:16px 20px;font-size:18px;font-weight:600">
<span style="display:inline-block;width:28px;height:28px;border-radius:14px;background:rgba(255,255,255,.12);color:{OCHRE};text-align:center;line-height:28px;margin-right:8px">अ</span>AnnRakshak</td></tr>
<tr><td style="padding:20px">{body}</td></tr>
<tr><td style="padding:14px 20px;background:#faf7f1;font-size:11px;line-height:1.5;color:#6b5b4b">{footer}</td></tr>
</table></td></tr></table></body></html>"""


def _h(text: str) -> str:
    return f'<p style="margin:18px 0 8px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#8a7a6a;font-weight:600">{_e(text)}</p>'


def _card(title: str, text: str, do: list[str], color: str, extra: str = "") -> str:
    items = "".join(f'<li style="margin:2px 0">{_e(x)}</li>' for x in do)
    return (f'<div style="border-left:4px solid {color};background:#fbf8f3;border-radius:10px;padding:12px 14px;margin:8px 0">'
            f'<p style="margin:0;font-weight:600;font-size:15px;color:{color}">{_e(title)}</p>'
            f'<p style="margin:6px 0 0;font-size:14px;line-height:1.45">{_e(text)}</p>'
            + (f'<ul style="margin:8px 0 0;padding-left:18px;font-size:13px;line-height:1.45">{items}</ul>' if do else "")
            + extra + '</div>')


def _button(url: str, label: str) -> str:
    return (f'<p style="margin:20px 0 4px"><a href="{_e(url)}" style="display:inline-block;background:{LEAF};color:{CREAM};'
            f'text-decoration:none;padding:12px 22px;border-radius:999px;font-weight:600;font-size:14px">{_e(label)}</a></p>')


def _now_table(cur: dict, lang: str) -> str:
    cells = [
        (t("temp", lang), f"{cur.get('temp')}°C" + (f" · {t('feels', lang)} {cur.get('feels')}°C" if cur.get("feels") is not None else "")),
        (t("rh", lang), f"{cur.get('rh')}%"),
        (t("wind", lang), f"{cur.get('wind')} km/h" + (f" · {t('gust', lang)} {cur.get('gust')}" if cur.get("gust") is not None else "")),
        (t("rain_chance", lang), f"{cur.get('prob_3h')}%" if cur.get("prob_3h") is not None else "—"),
        (t("uv", lang), str(cur.get("uv")) if cur.get("uv") is not None else "—"),
    ]
    rows = "".join(f'<tr><td style="padding:4px 0;color:#8a7a6a;font-size:13px">{_e(k)}</td>'
                   f'<td style="padding:4px 0;text-align:right;font-size:14px;font-weight:600">{_e(v)}</td></tr>' for k, v in cells)
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>'


def _days_table(days: list[dict]) -> str:
    rows = "".join(
        f'<tr><td style="padding:4px 0;font-size:13px">{_e(d["label"])}</td>'
        f'<td style="padding:4px 0;font-size:13px;text-align:center">{_e(d.get("tmin"))}–{_e(d.get("tmax"))}°C</td>'
        f'<td style="padding:4px 0;font-size:13px;text-align:right;color:#1d5e8a">{_e(d.get("rain"))} mm · {_e(d.get("prob"))}%</td></tr>'
        for d in days)
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>'


def _footer(d: dict, lang: str) -> str:
    return (_e(t("why_this", lang, crop=d["farm"]["crop_name"], district=d["farm"]["district"], source=d["source"]))
            + f'<br><a href="{_e(d["unsubscribe_url"])}" style="color:#6b5b4b">{_e(t("unsubscribe", lang))}</a>')


def _plain(parts: list[str]) -> str:
    return re.sub(r"\n{3,}", "\n\n", "\n".join(parts)).strip() + "\n"


# --------------------------------------------------------------------------
# The two emails
# --------------------------------------------------------------------------

def digest(d: dict, lang: str) -> tuple[str, str, str]:
    """(subject, text, html) for the daily summary. `d` from notify.digest_data()."""
    f, w = d["farm"], d["weather"]
    warn = [a for a in w["advisories"] if a["severity"] == "warning"]
    subject = ("⚠ " if warn else "") + t("digest_subject", lang, crop=f["crop_name"], date=d["date_label"])
    intro = t("digest_intro", lang, crop=f["crop_name"], district=f["district"], sowing=f["sowing"],
              stage=f["stage_name"], das=f["das"])
    body = [f'<p style="margin:0 0 6px;font-size:15px">{_e(t("hello", lang, name=f["name"]))}</p>',
            f'<p style="margin:0;font-size:14px;line-height:1.5">{_e(intro)}</p>']
    text = [t("hello", lang, name=f["name"]), intro, ""]

    advs = [a for a in w["advisories"] if a["rule"] != "spray_window"]
    body.append(_h(t("todo", lang)))
    text.append(f"== {t('todo', lang)} ==")
    if advs:
        for a in advs[:5]:
            body.append(_card(a["title"], a["text"], a["do"][:3], SEV_COLOR[a["severity"]]))
            text += [f"* {a['title']}", f"  {a['text']}"] + [f"  - {x}" for x in a["do"][:3]]
    else:
        body.append(f'<p style="margin:0;font-size:14px;color:{LEAF}">✓ {_e(t("all_calm", lang))}</p>')
        text.append(t("all_calm", lang))

    cur = w["current"]
    body += [_h(t("now", lang)), _now_table(cur, lang), _h(t("next3", lang)), _days_table(d["days3"])]
    text += ["", f"== {t('now', lang)} ==",
             f"{t('temp', lang)}: {cur.get('temp')}°C ({t('feels', lang)} {cur.get('feels')}°C) · {t('rh', lang)} {cur.get('rh')}%"
             f" · {t('wind', lang)} {cur.get('wind')} km/h · {t('rain_chance', lang)} {cur.get('prob_3h')}% · UV {cur.get('uv')}",
             f"== {t('next3', lang)} =="] + [f"{x['label']}: {x.get('tmin')}–{x.get('tmax')}°C, {x.get('rain')} mm ({x.get('prob')}%)" for x in d["days3"]]

    soil_bits = []
    if d.get("ph"):
        ph = d["ph"]
        soil_bits.append(f"{t('ph', lang)} {ph['value']} — {ph['band']} ({t('how_' + ph['how'], lang)})")
    if d.get("moisture_pct") is not None:
        soil_bits.append(f"{t('moisture', lang)}: {d['moisture_pct']}%")
    if soil_bits:
        body += [_h(t("soil", lang))] + [f'<p style="margin:2px 0;font-size:14px">{_e(x)}</p>' for x in soil_bits]
        text += ["", f"== {t('soil', lang)} =="] + soil_bits

    wb = w["water"]
    if wb.get("available"):
        line = t("wb", lang, etc=wb["etc_week"], rain=wb["eff_rain_week"], deficit=wb["deficit"])
        verdict = t("wb_" + wb["verdict"], lang)
        body += [_h(t("water", lang)), f'<p style="margin:2px 0;font-size:14px">{_e(line)}</p>',
                 f'<p style="margin:2px 0;font-size:14px;font-weight:600">{_e(verdict)}</p>']
        text += ["", f"== {t('water', lang)} ==", line, verdict]

    spray_line = t("spray_best", lang, when=d["spray_label"]) if d.get("spray_label") else t("spray_none", lang)
    body += [_h(t("spray", lang)), f'<p style="margin:2px 0;font-size:14px">{_e(spray_line)}</p>']
    text += ["", f"== {t('spray', lang)} ==", spray_line]

    if d["risks"]:
        body.append(_h(t("risks", lang)))
        text += ["", f"== {t('risks', lang)} =="]
        for r in d["risks"]:
            prev = r["prevention"]
            extra = ""
            if prev.get("avoid"):
                extra += f'<p style="margin:8px 0 0;font-size:13px;color:{EMBER}">✕ {_e(prev["avoid"][0])}</p>'
            body.append(_card(f'{r["name"]} · {r["level_label"]}', r["reason"], prev.get("do", []),
                              LEVEL_COLOR.get(r["level"], OCHRE), extra))
            text += [f"* {r['name']} ({r['level_label']}): {r['reason']}"] + [f"  - {x}" for x in prev.get("do", [])]
            if prev.get("avoid"):
                text.append(f"  x {prev['avoid'][0]}")

    body.append(_button(d["app_url"], t("open_app", lang)))
    text += ["", f"{t('open_app', lang)}: {d['app_url']}", "", t("unsubscribe", lang) + ": " + d["unsubscribe_url"]]
    preheader = warn[0]["title"] if warn else t("all_calm", lang)
    return subject, _plain(text), _shell(subject, "".join(body), _footer(d, lang), preheader)


def alert(d: dict, advs: list[dict], lang: str) -> tuple[str, str, str]:
    """(subject, text, html) for warnings that fired just now."""
    f = d["farm"]
    subject = "⚠ " + advs[0]["title"] + (f" (+{len(advs) - 1})" if len(advs) > 1 else "")
    intro = t("alert_intro", lang, crop=f["crop_name"], district=f["district"])
    body = [f'<p style="margin:0 0 6px;font-size:15px">{_e(t("hello", lang, name=f["name"]))}</p>',
            f'<p style="margin:0;font-size:14px">{_e(intro)}</p>']
    text = [t("hello", lang, name=f["name"]), intro, ""]
    for a in advs:
        body.append(_card(a["title"], a["text"], a["do"], SEV_COLOR[a["severity"]]))
        text += [f"* {a['title']}", f"  {a['text']}"] + [f"  - {x}" for x in a["do"]]
    cur = d["weather"]["current"]
    body += [_h(t("now", lang)), _now_table(cur, lang), _button(d["app_url"], t("open_app", lang))]
    text += ["", f"{t('open_app', lang)}: {d['app_url']}", "", t("unsubscribe", lang) + ": " + d["unsubscribe_url"]]
    return subject, _plain(text), _shell(subject, "".join(body), _footer(d, lang), advs[0]["text"])


def test_message(d: dict, lang: str) -> tuple[str, str, str]:
    f = d["farm"]
    subject = t("test_subject", lang, crop=f["crop_name"])
    msg = t("test_body", lang)
    body = (f'<p style="margin:0 0 6px;font-size:15px">{_e(t("hello", lang, name=f["name"]))}</p>'
            f'<p style="margin:0;font-size:14px">{_e(msg)}</p>' + _button(d["app_url"], t("open_app", lang)))
    return subject, _plain([t("hello", lang, name=f["name"]), msg, "", d["app_url"]]), _shell(subject, body, _footer(d, lang), msg)


def otp_message(code: str, purpose: str, mins: int, lang: str) -> tuple[str, str, str]:
    """The one-time code email (sign-up or sign-in)."""
    subject = t("otp_subject", lang, code=code)
    lead, expiry, warn = t(f"otp_{purpose}", lang), t("otp_expiry", lang, mins=mins), t("otp_warn", lang)
    body = (f'<p style="margin:0 0 14px;font-size:15px">{_e(lead)}</p>'
            f'<p style="margin:0 0 14px;font-size:32px;letter-spacing:10px;font-weight:700;color:{LEAF};'
            f'font-family:Menlo,Consolas,monospace">{_e(code)}</p>'
            f'<p style="margin:0;font-size:13px;color:#6b5b4b">{_e(expiry)}</p>')
    return subject, _plain([lead, "", code, "", expiry, "", warn]), _shell(subject, body, _e(warn), lead)


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def valid_address(addr: str) -> bool:
    return bool(EMAIL_RE.match(addr or "")) and len(addr) <= 200


def send(to: str, subject: str, text: str, html_body: str, *, unsubscribe_url: str | None = None) -> tuple[str, str | None]:
    """Returns (status, error): ('sent'|'outbox', None) or ('failed', reason). Never raises."""
    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="annrakshak.in")
    if unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    try:
        if EMAIL_BACKEND == "smtp" and SMTP_HOST:
            if SMTP_SECURITY == "ssl":
                server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
                if SMTP_SECURITY == "starttls":
                    server.starttls(context=ssl.create_default_context())
            with server:
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD or "")
                server.send_message(msg)
            return "sent", None
        OUTBOX.mkdir(parents=True, exist_ok=True)
        name = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.eml"
        (OUTBOX / name).write_bytes(bytes(msg))
        return "outbox", None
    except (smtplib.SMTPException, OSError) as e:
        # The class and SMTP code only: a server's error text can echo the login.
        code = getattr(e, "smtp_code", None)
        return "failed", f"{type(e).__name__}{f' {code}' if code else ''}"
