"""Farm emails: an alert right away when a warning fires, a short morning
summary, the sign-in code, and the note that alerts are on. Written in the
farmer's language from the farm profile.

Each is read on a phone, often in a hurry: the summary is a traffic light —
one row each for water, spraying and pests (and the weather when it warns),
a coloured dot and a verdict before any explanation — then three days of
weather. Everything else is one tap away in the app.

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
from pathlib import Path

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
EMBLEM = Path(__file__).parent / "assets" / "emblem-192.png"
EMBLEM_CID = "emblem@annrakshak"
"""The emblem travels inside the email (an inline image), so it shows before
the app has a public address and in clients that block remote images."""

LEAF, CREAM, PAPER, INK, MUTED, LINE = "#1d4a2c", "#f6f1e7", "#ffffff", "#21180f", "#6b5e50", "#efe8dc"
RED, AMBER, GREEN, GREY = "#c2412d", "#d08a1e", "#2f7d4a", "#9a9187"
LEVEL_COLOR = {"high": RED, "medium": AMBER, "low": GREY}
TINT = {RED: ("#fbeeeb", "#efc9c1"), AMBER: ("#fcf4e6", "#ecd3a5")}
"""Background and border for a warning card (8-digit hex is not safe in mail clients)."""
SANS = "-apple-system,'Segoe UI',Roboto,'Noto Sans','Noto Sans Devanagari',Arial,sans-serif"
SERIF = "Georgia,'Noto Serif','Noto Serif Devanagari',serif"

T = {
    "motto": {"en": "Protector of the Harvest", "hi": "फ़सल का रक्षक", "mr": "पिकांचा रक्षक"},
    # the summary
    "digest_subject": {"en": "Your {crop} today: {top}", "hi": "आज आपकी फसल ({crop}): {top}",
                       "mr": "आज तुमचे पीक {crop}: {top}"},
    "all_ok": {"en": "all calm", "hi": "सब ठीक", "mr": "सर्व ठीक"},
    "greet": {"en": "{name}, your {crop}", "hi": "{name} जी, आपकी फसल: {crop}", "mr": "{name}, तुमचे पीक {crop}"},
    "where": {"en": "Day {das} · {stage} · {district}", "hi": "दिन {das} · {stage} · {district}",
              "mr": "दिवस {das} · {stage} · {district}"},
    "water": {"en": "Water", "hi": "पानी", "mr": "पाणी"},
    "spray": {"en": "Spray", "hi": "छिड़काव", "mr": "फवारणी"},
    "pests": {"en": "Pests", "hi": "कीट-रोग", "mr": "कीड-रोग"},
    "weather": {"en": "Weather", "hi": "मौसम", "mr": "हवामान"},
    "w_irrigate": {"en": "Irrigate today", "hi": "आज सिंचाई करें", "mr": "आज पाणी द्या"},
    "w_irrigate_why": {"en": "{deficit} mm short this week, no useful rain ahead",
                       "hi": "इस हफ़्ते {deficit} मिमी पानी कम, आगे काम की बारिश नहीं",
                       "mr": "या आठवड्यात {deficit} मिमी पाणी कमी, पुढे उपयोगी पाऊस नाही"},
    "w_hold_rain": {"en": "Hold irrigation", "hi": "सिंचाई रोकें", "mr": "पाणी देणे थांबवा"},
    "w_hold_rain_why": {"en": "Useful rain is on the way", "hi": "काम की बारिश आने वाली है",
                        "mr": "उपयोगी पाऊस येणार आहे"},
    "w_ok": {"en": "No water needed", "hi": "अभी पानी की ज़रूरत नहीं", "mr": "सध्या पाण्याची गरज नाही"},
    "w_ok_why": {"en": "The soil has enough for now", "hi": "मिट्टी में अभी पर्याप्त पानी है",
                 "mr": "मातीत सध्या पुरेसे पाणी आहे"},
    "w_stop_stage": {"en": "Stop irrigating", "hi": "सिंचाई बंद करें", "mr": "पाणी देणे बंद करा"},
    "w_stop_stage_why": {"en": "The crop is ripening", "hi": "फसल पक रही है", "mr": "पीक पिकत आहे"},
    "s_best": {"en": "Spray {when}", "hi": "{when} छिड़काव करें", "mr": "{when} फवारणी करा"},
    "s_best_why": {"en": "Dry and calm then", "hi": "तब मौसम सूखा और शांत रहेगा", "mr": "तेव्हा हवामान कोरडे व शांत असेल"},
    "s_none": {"en": "Don't spray yet", "hi": "अभी छिड़काव न करें", "mr": "आत्ता फवारणी करू नका"},
    "s_none_why": {"en": "No dry, calm spell in the next 48 hours", "hi": "अगले 48 घंटे में सूखा, शांत समय नहीं",
                   "mr": "पुढील 48 तासांत कोरडी, शांत वेळ नाही"},
    "p_none": {"en": "Nothing favoured now", "hi": "अभी किसी का ख़तरा नहीं", "mr": "सध्या कशाचाही धोका नाही"},
    "p_none_why": {"en": "The weather is not setting up a pest or disease", "hi": "मौसम किसी कीट या रोग के अनुकूल नहीं",
                   "mr": "हवामान कोणत्याही कीड किंवा रोगाला पोषक नाही"},
    "p_also": {"en": "Also watch: {names}", "hi": "इन पर भी नज़र रखें: {names}", "mr": "यांच्यावरही लक्ष ठेवा: {names}"},
    "now_line": {"en": "Now {temp}° · humidity {rh}% · wind {wind} km/h",
                 "hi": "अभी {temp}° · नमी {rh}% · हवा {wind} किमी/घं",
                 "mr": "आत्ता {temp}° · आर्द्रता {rh}% · वारा {wind} किमी/तास"},
    "soil_line": {"en": "Soil pH {ph}, {band}", "hi": "मिट्टी: pH (सामू) {ph}, {band}",
                  "mr": "माती: सामू (pH) {ph}, {band}"},
    "moisture": {"en": "moisture {pct}%", "hi": "नमी {pct}%", "mr": "ओलावा {pct}%"},
    "open_field": {"en": "Open my field", "hi": "मेरा खेत खोलें", "mr": "माझे शेत उघडा"},
    "sources": {"en": "Live weather from {source}. Advice from ICAR and IMD. For any product, its label decides.",
                "hi": "ताज़ा मौसम {source} से। सलाह ICAR और IMD से। किसी भी दवा के लिए उसका लेबल ही मान्य है।",
                "mr": "ताजे हवामान {source} कडून. सल्ला ICAR आणि IMD कडून. कोणत्याही औषधासाठी त्याचे लेबलच ग्राह्य."},
    "unsubscribe": {"en": "Stop these emails", "hi": "ये ईमेल बंद करें", "mr": "हे ईमेल बंद करा"},
    # a warning, right away
    "alert_greet": {"en": "{name}, a warning for your {crop}", "hi": "{name} जी, {crop} के लिए चेतावनी",
                    "mr": "{name}, तुमच्या {crop} पिकासाठी इशारा"},
    "do_now": {"en": "Do now", "hi": "अभी करें", "mr": "आत्ता करा"},
    # alerts are on
    "test_subject": {"en": "AnnRakshak: email alerts are on for {crop}", "hi": "AnnRakshak: {crop} के लिए ईमेल अलर्ट चालू",
                     "mr": "AnnRakshak: {crop} साठी ईमेल सूचना सुरू"},
    "test_title": {"en": "Email alerts are on", "hi": "ईमेल अलर्ट चालू हैं", "mr": "ईमेल सूचना सुरू आहेत"},
    "test_warn": {"en": "Warnings: the moment they come", "hi": "चेतावनी: आते ही तुरंत", "mr": "इशारे: येताच लगेच"},
    "test_daily": {"en": "Summary: every morning at 6", "hi": "सारांश: हर सुबह 6 बजे", "mr": "सारांश: दररोज सकाळी 6 वाजता"},
    # the one-time code
    "otp_subject": {"en": "{code} is your AnnRakshak code", "hi": "{code} आपका AnnRakshak कोड है",
                    "mr": "{code} हा तुमचा AnnRakshak कोड आहे"},
    "otp_login": {"en": "Your sign-in code", "hi": "आपका साइन-इन कोड", "mr": "तुमचा साइन-इन कोड"},
    "otp_signup": {"en": "Your sign-up code", "hi": "आपका साइन-अप कोड", "mr": "तुमचा साइन-अप कोड"},
    "otp_email": {"en": "Confirm your email", "hi": "अपना ईमेल पक्का करें", "mr": "तुमचा ईमेल निश्चित करा"},
    "otp_valid": {"en": "Works for {mins} minutes, once", "hi": "{mins} मिनट तक, एक बार चलेगा",
                  "mr": "{mins} मिनिटे, एकदाच चालेल"},
    "otp_never": {"en": "Don't share it. Nobody from AnnRakshak or KVK will ever ask for it.",
                  "hi": "किसी को न बताएँ। AnnRakshak या KVK से कोई इसे कभी नहीं माँगेगा।",
                  "mr": "कोणालाही सांगू नका. AnnRakshak किंवा KVK कडून कोणीही तो कधीही मागणार नाही."},
    "otp_ignore": {"en": "Didn't ask for it? Ignore this email.", "hi": "आपने नहीं माँगा? इस ईमेल को अनदेखा करें।",
                   "mr": "तुम्ही मागितला नाही? हा ईमेल दुर्लक्षित करा."},
}


def t(key: str, lang: str, **kw) -> str:
    s = tr(T[key], lang)
    return s.format(**kw) if kw else s


def _e(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _n(x, digits: int = 0) -> str:
    """28.3 -> '28'; 0.04 -> '0'; 12.5 mm -> '12.5'."""
    if x is None:
        return "—"
    v = round(float(x), digits)
    return f"{v:.{digits}f}".rstrip("0").rstrip(".") if digits else str(int(v))


def _first(name: str | None) -> str:
    return (name or "").split()[0] if (name or "").strip() else ""


# --------------------------------------------------------------------------
# Building blocks (tables and inline styles: most mail clients strip <style>)
# --------------------------------------------------------------------------

def _shell(title: str, body: str, footer: str, preheader: str, lang: str) -> str:
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta name="color-scheme" content="light"><title>{_e(title)}</title></head>
<body style="margin:0;padding:0;background:{CREAM};font-family:{SANS};color:{INK};-webkit-text-size-adjust:100%">
<span style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">{_e(preheader)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM}"><tr><td align="center" style="padding:20px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:{PAPER};border-radius:20px;overflow:hidden;border:1px solid #e6dccb">
<tr><td style="background:{LEAF};padding:18px 22px">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td style="padding-right:12px"><img src="cid:{EMBLEM_CID}" width="44" height="44" alt="" style="display:block;border-radius:22px;background:#ffffff"></td>
<td><div style="font-size:19px;font-weight:700;color:{CREAM};letter-spacing:-.01em">AnnRakshak</div>
<div style="font-size:12px;color:#cfd9cf;margin-top:1px">{_e(t("motto", lang))}</div></td>
</tr></table></td></tr>
{body}
<tr><td style="padding:16px 22px 20px;font-size:11px;line-height:1.55;color:#8a7d6e;border-top:1px solid {LINE}">{footer}</td></tr>
</table></td></tr></table></body></html>"""


def _title(big: str, small: str | None = None) -> str:
    return (f'<tr><td style="padding:22px 22px 6px"><div style="font-family:{SERIF};font-size:24px;line-height:1.2;'
            f'color:{INK}">{_e(big)}</div>'
            + (f'<div style="font-size:13px;color:{MUTED};margin-top:4px">{_e(small)}</div>' if small else "")
            + '</td></tr>')


def _row(color: str, label: str, verdict: str, why: str, lang: str, last: bool = False) -> str:
    # Spacing out letters breaks the joined letters of Indian scripts.
    spaced = "letter-spacing:.09em;text-transform:uppercase;" if lang == "en" else ""
    rule = "" if last else f"border-bottom:1px solid {LINE};"
    return (f'<tr><td width="34" valign="top" style="padding:16px 0 0 22px">'
            f'<div style="width:14px;height:14px;border-radius:7px;background:{color}"></div></td>'
            f'<td style="padding:13px 22px 13px 4px;{rule}">'
            f'<div style="font-size:11px;font-weight:700;color:#8a7d6e;{spaced}">{_e(label)}</div>'
            f'<div style="font-size:17px;font-weight:700;color:{INK};margin-top:2px;line-height:1.3">{_e(verdict)}</div>'
            + "".join(f'<div style="font-size:13px;color:{MUTED if i == 0 else "#8a7d6e"};margin-top:{3 if i == 0 else 6}px;'
                      f'line-height:1.45">{_e(x)}</div>' for i, x in enumerate(why.split("\n")) if x)
            + '</td></tr>')


def _rows(rows: list[tuple[str, str, str, str]], lang: str) -> str:
    inner = "".join(_row(*r, lang=lang, last=i == len(rows) - 1) for i, r in enumerate(rows))
    return (f'<tr><td style="padding:10px 12px 4px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="background:#fbf8f2;border:1px solid {LINE};border-radius:16px">{inner}</table></td></tr>')


def _sky(day: dict) -> str:
    rain, prob = float(day.get("rain") or 0), float(day.get("prob") or 0)
    if rain >= 5 or prob >= 60:
        return "🌧"
    if rain >= 1 or prob >= 30:
        return "🌦"
    return "☀️"


def _days(days: list[dict]) -> str:
    cells = "".join(
        f'<td width="33%" style="padding:0 4px"><div style="background:{CREAM};border-radius:14px;padding:10px 6px;text-align:center">'
        f'<div style="font-size:12px;color:{MUTED}">{_e(d["label"][:1].upper() + d["label"][1:])}</div>'
        f'<div style="font-size:22px;line-height:1.3;margin:2px 0">{_sky(d)}</div>'
        f'<div style="font-size:15px;font-weight:700;color:{INK}">{_n(d.get("tmax"))}°'
        f'<span style="font-weight:400;color:{MUTED}"> / {_n(d.get("tmin"))}°</span></div>'
        f'<div style="font-size:12px;color:#2f6c8f;margin-top:2px">{_n(d.get("rain"), 1)} mm</div></div></td>'
        for d in days[:3])
    return (f'<tr><td style="padding:14px 18px 2px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{cells}</tr></table></td></tr>')


def _small(lines: list[str]) -> str:
    return (f'<tr><td style="padding:10px 22px 0;font-size:12px;line-height:1.6;color:{MUTED};text-align:center">'
            + "<br>".join(_e(x) for x in lines if x) + '</td></tr>')


def _button(url: str, label: str) -> str:
    return (f'<tr><td align="center" style="padding:20px 22px 22px"><a href="{_e(url)}" style="display:inline-block;'
            f'background:{LEAF};color:{CREAM};text-decoration:none;padding:13px 26px;border-radius:999px;font-weight:700;'
            f'font-size:15px">{_e(label)} &rarr;</a></td></tr>')


def _footer(d: dict, lang: str) -> str:
    return (_e(t("sources", lang, source=d["source"]))
            + f'<br><a href="{_e(d["unsubscribe_url"])}" style="color:#8a7d6e">{_e(t("unsubscribe", lang))}</a>')


def _plain(parts: list[str]) -> str:
    return re.sub(r"\n{3,}", "\n\n", "\n".join(parts)).strip() + "\n"


# --------------------------------------------------------------------------
# The summary: a traffic light
# --------------------------------------------------------------------------

WEATHER_RULES = ("thunderstorm", "heavy_rain", "strong_wind", "frost", "heat_crop", "cold", "fog", "heat_people",
                 "fungal_weather", "greenness_drop")


def lights(d: dict, lang: str) -> list[tuple[str, str, str, str]]:
    """(colour, label, verdict, why) for each row, most urgent weather first."""
    w = d["weather"]
    rows: list[tuple[str, str, str, str]] = []
    weather = [a for a in w["advisories"] if a["rule"] in WEATHER_RULES]
    if weather:
        a = weather[0]
        rows.append((RED if a["severity"] == "warning" else AMBER, t("weather", lang), a["title"],
                     (a.get("do") or [a.get("text", "")])[0]))

    wb = w.get("water") or {}
    if wb.get("available"):
        v = wb["verdict"]
        color = {"irrigate": RED, "hold_rain": GREEN, "ok": GREEN, "stop_stage": GREY}.get(v, GREY)
        why = t(f"w_{v}_why", lang, deficit=_n(wb.get("deficit"))) if v in ("irrigate", "hold_rain", "ok", "stop_stage") else ""
        rows.append((color, t("water", lang), t(f"w_{v}", lang), why))

    rain_after = next((a for a in w["advisories"] if a["rule"] == "rain_after_spray"), None)
    if rain_after:
        rows.append((RED, t("spray", lang), rain_after["title"], (rain_after.get("do") or [rain_after["text"]])[0]))
    elif d.get("spray_label"):
        rows.append((GREEN, t("spray", lang), t("s_best", lang, when=d["spray_label"]), t("s_best_why", lang)))
    else:
        rows.append((AMBER, t("spray", lang), t("s_none", lang), t("s_none_why", lang)))

    risks = d.get("risks") or []
    if risks:
        r = risks[0]
        prev = r.get("prevention") or {}
        why = (prev.get("avoid") or prev.get("do") or [""])[0]
        rows.append((LEVEL_COLOR.get(r["level"], AMBER), t("pests", lang), f'{r["name"]} · {r["level_label"]}', why))
        if len(risks) > 1:
            rows[-1] = rows[-1][:3] + (why + ("\n" if why else "") + t("p_also", lang, names=", ".join(x["name"] for x in risks[1:])),)
    else:
        rows.append((GREEN, t("pests", lang), t("p_none", lang), t("p_none_why", lang)))
    return rows


def digest(d: dict, lang: str) -> tuple[str, str, str]:
    """(subject, text, html) for the morning summary. `d` from notify.digest_data()."""
    f, w = d["farm"], d["weather"]
    rows = lights(d, lang)
    urgent = [r for r in rows if r[0] in (RED, AMBER)]
    top = urgent[0][2] if urgent else t("all_ok", lang)
    subject = ("⚠ " if any(r[0] == RED for r in rows) else "") + t("digest_subject", lang, crop=f["crop_name"], top=top)
    name = _first(f["name"])
    greet = t("greet", lang, name=name, crop=f["crop_name"]) if name else f["crop_name"]
    where = t("where", lang, das=f["das"], stage=f["stage_name"], district=f["district"])

    cur = w["current"]
    now_line = t("now_line", lang, temp=_n(cur.get("temp")), rh=_n(cur.get("rh")), wind=_n(cur.get("wind")))
    soil = []
    if d.get("ph"):
        soil.append(t("soil_line", lang, ph=d["ph"]["value"], band=d["ph"]["band"]))
    if d.get("moisture_pct") is not None:
        soil.append(t("moisture", lang, pct=_n(d["moisture_pct"])))
    soil_line = " · ".join(soil)

    body = (_title(greet, where) + _rows(rows, lang)
            + _days(d["days3"]) + _small([now_line, soil_line]) + _button(d["app_url"], t("open_field", lang)))
    text = [greet, where, ""]
    for _, label, verdict, why in rows:
        text += [f"{label}: {verdict}"] + [f"  {x}" for x in why.split("\n") if x]
    text += ["", "  ".join(f"{x['label']} {_n(x.get('tmax'))}°/{_n(x.get('tmin'))}° {_n(x.get('rain'), 1)} mm"
                           for x in d["days3"][:3]), now_line, soil_line, "",
             f"{t('open_field', lang)}: {d['app_url']}", "", f"{t('unsubscribe', lang)}: {d['unsubscribe_url']}"]
    preheader = " · ".join(r[2] for r in rows)
    return subject, _plain(text), _shell(subject, body, _footer(d, lang), preheader, lang)


# --------------------------------------------------------------------------
# A warning, the moment it fires
# --------------------------------------------------------------------------

def alert(d: dict, advs: list[dict], lang: str) -> tuple[str, str, str]:
    """(subject, text, html) for warnings that fired just now."""
    f = d["farm"]
    subject = "⚠ " + advs[0]["title"] + (f" (+{len(advs) - 1})" if len(advs) > 1 else "")
    name = _first(f["name"])
    greet = t("alert_greet", lang, name=name, crop=f["crop_name"]) if name else f["crop_name"]
    cards, text = [], [greet, ""]
    for a in advs:
        color = RED if a["severity"] == "warning" else AMBER
        do = "".join(f'<tr><td valign="top" style="padding:3px 8px 3px 0;color:{color};font-weight:700">&rarr;</td>'
                     f'<td style="padding:3px 0;font-size:14px;line-height:1.45;color:{INK}">{_e(x)}</td></tr>'
                     for x in a["do"][:3])
        cards.append(
            f'<tr><td style="padding:10px 12px 0"><div style="background:{TINT[color][0]};border:1px solid {TINT[color][1]};'
            f'border-radius:16px;padding:16px 18px">'
            f'<div style="font-size:18px;font-weight:700;color:{color};line-height:1.3">{_e(a["title"])}</div>'
            f'<div style="font-size:14px;color:{INK};margin-top:6px;line-height:1.5">{_e(a["text"])}</div>'
            + (f'<div style="font-size:11px;font-weight:700;color:#8a7d6e;margin-top:12px">{_e(t("do_now", lang))}</div>'
               f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:4px">{do}</table>' if do else "")
            + '</div></td></tr>')
        text += [a["title"], a["text"]] + [f"-> {x}" for x in a["do"][:3]] + [""]
    cur = d["weather"]["current"]
    now_line = t("now_line", lang, temp=_n(cur.get("temp")), rh=_n(cur.get("rh")), wind=_n(cur.get("wind")))
    body = _title(greet) + "".join(cards) + _small([now_line]) + _button(d["app_url"], t("open_field", lang))
    text += [now_line, "", f"{t('open_field', lang)}: {d['app_url']}", "", f"{t('unsubscribe', lang)}: {d['unsubscribe_url']}"]
    return subject, _plain(text), _shell(subject, body, _footer(d, lang), advs[0]["text"], lang)


# --------------------------------------------------------------------------
# Alerts are on; the one-time code
# --------------------------------------------------------------------------

def _ticks(lines: list[str]) -> str:
    rows = "".join(f'<tr><td style="padding:5px 10px 5px 0;color:{GREEN};font-weight:700">&#10003;</td>'
                   f'<td style="padding:5px 0;font-size:15px;color:{INK}">{_e(x)}</td></tr>' for x in lines)
    return f'<tr><td style="padding:8px 22px 0"><table role="presentation" cellpadding="0" cellspacing="0">{rows}</table></td></tr>'


def test_message(d: dict, lang: str) -> tuple[str, str, str]:
    f = d["farm"]
    subject = t("test_subject", lang, crop=f["crop_name"])
    title, lines = t("test_title", lang), [t("test_warn", lang), t("test_daily", lang)]
    body = _title(title, f'{f["crop_name"]} · {f["district"]}') + _ticks(lines) + _button(d["app_url"], t("open_field", lang))
    text = [title, *lines, "", d["app_url"], "", f"{t('unsubscribe', lang)}: {d['unsubscribe_url']}"]
    return subject, _plain(text), _shell(subject, body, _footer(d, lang), " · ".join(lines), lang)


def otp_message(code: str, purpose: str, mins: int, lang: str) -> tuple[str, str, str]:
    """The one-time code email (sign-up, sign-in, or confirming an address)."""
    subject = t("otp_subject", lang, code=code)
    title, valid, never = t(f"otp_{purpose}", lang), t("otp_valid", lang, mins=mins), t("otp_never", lang)
    body = (_title(title)
            + f'<tr><td style="padding:12px 22px 0"><div style="background:{CREAM};border:1px solid #e6dccb;border-radius:16px;'
              f'padding:18px 10px;text-align:center;font-family:Menlo,Consolas,\'Courier New\',monospace;font-size:34px;'
              f'font-weight:700;letter-spacing:10px;color:{LEAF}">{_e(code)}</div></td></tr>'
            + f'<tr><td style="padding:10px 22px 0;font-size:13px;color:{MUTED};text-align:center">{_e(valid)}</td></tr>'
            + f'<tr><td style="padding:16px 22px 22px"><div style="font-size:13px;line-height:1.5;color:{INK};'
              f'background:#fbf3e6;border-radius:12px;padding:10px 14px">&#128274;&nbsp; {_e(never)}</div></td></tr>')
    text = [title, "", code, "", valid, "", never, t("otp_ignore", lang)]
    return subject, _plain(text), _shell(subject, body, _e(t("otp_ignore", lang)), f"{code} · {valid}", lang)


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
    if f"cid:{EMBLEM_CID}" in html_body and EMBLEM.exists():
        msg.get_payload()[1].add_related(EMBLEM.read_bytes(), maintype="image", subtype="png", cid=f"<{EMBLEM_CID}>",
                                         filename="annrakshak.png", disposition="inline")
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
