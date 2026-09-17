"""Risk scoring: weather favourability, crop stage, trap counts, history.

Pure functions only — no database, no HTTP. The service layer fetches the
weather window, trap readings and history and hands them in; this module says
whether a rule fires, how strongly, and WHY in the farmer's language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.engine.weather import Day, Window
from app.i18n import LANGS
from app.kb import tr

LEVELS = ("low", "medium", "high")

REASONS = {
    "weather": {
        "en": "Humidity stayed above {rh}% with average temperature {tlo}–{thi}°C for {run} days in a row ({first} to {last}). These conditions favour {name}.",
        "hi": "{first} से {last} तक लगातार {run} दिन नमी {rh}% से ऊपर और औसत तापमान {tlo}–{thi}°C रहा। यह मौसम {name} के लिए अनुकूल है।",
        "mr": "{first} ते {last} सलग {run} दिवस आर्द्रता {rh}% पेक्षा जास्त व सरासरी तापमान {tlo}–{thi}°C राहिले. हे हवामान {name} साठी अनुकूल आहे.",
    },
    "phenology": {
        "en": "Your crop is {das} days old ({stage}) — the stage when {name} usually attacks. Check before damage shows.",
        "hi": "आपकी फसल {das} दिन की है ({stage}) — इसी अवस्था में {name} का हमला होता है। नुकसान दिखने से पहले जाँचें।",
        "mr": "तुमचे पीक {das} दिवसांचे आहे ({stage}) — याच अवस्थेत {name} चा प्रादुर्भाव होतो. नुकसान दिसण्यापूर्वी तपासा.",
    },
    "trap": {
        "en": "Your traps caught {rate} moths per trap per night for {n} nights in a row — above the action level of {etl}.",
        "hi": "आपके ट्रैप में लगातार {n} रात प्रति ट्रैप प्रति रात {rate} पतंगे आए — कार्रवाई सीमा {etl} से ज़्यादा।",
        "mr": "तुमच्या सापळ्यात सलग {n} रात्री प्रति सापळा प्रति रात्र {rate} पतंग आले — कृती मर्यादा {etl} पेक्षा जास्त.",
    },
    "spread": {
        "en": "An expert confirmed {name} on a {crop} farm {km} km from you.",
        "hi": "आपसे {km} किमी दूर एक {crop} खेत पर विशेषज्ञ ने {name} की पुष्टि की है।",
        "mr": "तुमच्यापासून {km} किमी अंतरावरील {crop} शेतावर तज्ज्ञांनी {name} ची खात्री केली आहे.",
    },
    "forecast": {
        "en": " The forecast shows these conditions continuing.",
        "hi": " पूर्वानुमान के अनुसार ऐसा मौसम आगे भी रहेगा।",
        "mr": " अंदाजानुसार असे हवामान पुढेही राहील.",
    },
    "history": {
        "en": " It was found on your farm before.",
        "hi": " यह पहले भी आपके खेत में मिला था।",
        "mr": " हे यापूर्वीही तुमच्या शेतात आढळले होते.",
    },
    "sensor": {
        "en": " (includes readings from your field sensor)",
        "hi": " (आपके खेत के सेंसर की रीडिंग सहित)",
        "mr": " (तुमच्या शेतातील सेन्सरच्या नोंदींसह)",
    },
}


@dataclass
class Score:
    target: str
    fired: bool
    level: str
    trigger: str
    reason: dict[str, str] = field(default_factory=dict)
    detail: dict = field(default_factory=dict)


def _bump(level: str) -> str:
    return LEVELS[min(LEVELS.index(level) + 1, len(LEVELS) - 1)]


def favourable(day: Day, w: dict) -> bool:
    """A day with a missing reading is NOT favourable — a data gap must not
    manufacture a consecutive-day run."""
    if day.rh_max is None or day.t_mean is None:
        return False
    if day.rh_max < w["rh_min"]:
        return False
    if not (w["t_min"] <= day.t_mean <= w["t_max"]):
        return False
    if "rain_min" in w and (day.rain_mm is None or day.rain_mm < w["rain_min"]):
        return False
    if "rain_max" in w and (day.rain_mm is None or day.rain_mm > w["rain_max"]):
        return False
    return True


def longest_run(days: list[Day], w: dict) -> tuple[int, Day | None, Day | None]:
    best, run = 0, 0
    best_first = best_last = first = None
    for d in days:
        if favourable(d, w):
            run += 1
            first = first if run > 1 else d
            if run > best:
                best, best_first, best_last = run, first, d
        else:
            run, first = 0, None
    return best, best_first, best_last


def _joined(parts: dict[str, str], lang: str) -> str:
    """A sentence appended to a reason. Stored with its leading space, which a
    translation memory keyed by stripped text would lose."""
    en = parts["en"]
    text = tr({k: v.strip() for k, v in parts.items()}, lang)
    return (" " if en[:1].isspace() else "") + text


def _fmt_date(d: date, lang: str) -> str:
    return d.strftime("%d %b") if lang == "en" else d.strftime("%d/%m")


DATE_ARGS = ("first", "last")


def _render_parts(parts: list[dict], lang: str) -> str:
    out = ""
    for p in parts:
        args = {k: tr(v, lang) if isinstance(v, dict) else _fmt_date(date.fromisoformat(v), lang) if k in DATE_ARGS
                else v for k, v in p.get("args", {}).items()}
        tmpl = REASONS[p["key"]]
        out += (_joined(tmpl, lang) if tmpl["en"][:1].isspace() else tr(tmpl, lang)).format(**args)
    return out


def reason_of(parts: list[dict]) -> dict:
    """A reason in every language, plus the parts it was built from ('_parts':
    template keys and values), so it can be rendered again in any language —
    including one whose translation arrived after the alert was issued."""
    return {lang: _render_parts(parts, lang) for lang in LANGS} | {"_parts": parts}


def reason_text(reason: dict | None, lang: str) -> str:
    """An alert's reason in `lang`: from its parts when stored, else the frozen text."""
    if reason and reason.get("_parts"):
        try:
            return _render_parts(reason["_parts"], lang)
        except (KeyError, ValueError):
            pass
    return tr(reason, lang)


def score_rule(
    target: str,
    rule: dict,
    *,
    target_name: dict[str, str],
    stage: str,
    stage_name: dict[str, str],
    das: int,
    window: Window | None,
    has_history: bool,
    today: date | None = None,
) -> Score:
    """Weather and/or phenology. Trap and spread are scored separately because
    they are driven by events, not by the calendar."""
    today = today or date.today()
    w, ph = rule.get("weather"), rule.get("phenology")
    if not w and not ph:
        return Score(target, False, "low", "none", detail={"why": "trap-only rule"})

    if stage not in rule.get("stages", []):
        return Score(target, False, "low", "none", detail={"why": f"stage {stage} not susceptible"})

    if ph and not (ph["das_min"] <= das <= ph["das_max"]):
        return Score(target, False, "low", "none", detail={"why": f"DAS {das} outside window"})

    detail: dict = {"stage": stage, "das": das}
    if w:
        if window is None:
            return Score(target, False, "low", "none", detail={"why": "no weather window"})
        run, first, last = longest_run(window.days, w)
        detail |= {"run": run, "needed": w["days"], "weather_source": window.source}
        if run < w["days"]:
            detail["why"] = f"favourable run {run} < {w['days']}"
            return Score(target, False, "low", "none", detail=detail)
        includes_forecast = last is not None and last.on > today
        used_sensor = any(d.from_sensor for d in window.days)
        level = "high" if run >= w["days"] + 3 else "medium"
        parts = [{"key": "weather", "args": {"rh": w["rh_min"], "tlo": w["t_min"], "thi": w["t_max"], "run": run,
                                             "first": first.on.isoformat(), "last": last.on.isoformat(),
                                             "name": target_name}}]
        if includes_forecast:
            parts.append({"key": "forecast"})
        if used_sensor:
            parts.append({"key": "sensor"})
        detail |= {"first": first.on.isoformat(), "last": last.on.isoformat(),
                   "includes_forecast": includes_forecast, "used_sensor": used_sensor}
        trigger = "weather+phenology" if ph else "weather"
    else:
        level = "low"
        parts = [{"key": "phenology", "args": {"das": das, "stage": stage_name, "name": target_name}}]
        trigger = "phenology"

    if has_history:
        level = _bump(level)
        parts.append({"key": "history"})
        detail["history_bump"] = True

    return Score(target, True, level, trigger, reason_of(parts), detail)


def score_traps(target: str, rule: dict, readings: list[dict], today: date | None = None) -> Score:
    """readings: [{recorded_on, count, traps, nights}] for this farm+target.

    Each reading covers `nights` nights ending on recorded_on. The rule fires
    when the most recent `rule.trap.nights` nights all met the ETL."""
    trap = rule.get("trap")
    if not trap or not readings:
        return Score(target, False, "low", "trap")
    today = today or date.today()
    nightly: dict[date, float] = {}
    for r in readings:
        rate = r["count"] / (r["traps"] * r["nights"])
        for i in range(r["nights"]):
            nightly[r["recorded_on"] - timedelta(days=i)] = rate
    need, etl = trap["nights"], trap["etl_per_trap_night"]
    latest = max(nightly)
    if (today - latest).days > 3:
        return Score(target, False, "low", "trap", detail={"why": "no recent readings"})
    streak, rates = 0, []
    d = latest
    while d in nightly and nightly[d] >= etl:
        streak += 1
        rates.append(nightly[d])
        d -= timedelta(days=1)
    detail = {"streak": streak, "needed": need, "etl": etl, "latest": latest.isoformat()}
    if streak < need:
        return Score(target, False, "low", "trap", detail=detail)
    rate = round(sum(rates[:need]) / need, 1)
    reason = reason_of([{"key": "trap", "args": {"rate": rate, "n": streak, "etl": etl}}])
    return Score(target, True, "high", "trap", reason, detail | {"rate": rate})


def spread_reason(target_name: dict[str, str], crop_name: dict[str, str], km: float) -> dict[str, str]:
    return reason_of([{"key": "spread", "args": {"name": target_name, "crop": crop_name, "km": f"{km:.1f}"}}])
