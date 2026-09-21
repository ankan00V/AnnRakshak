"""Live field walk: context at the start, persistence and the spoken summary at
the end. The per-frame logic lives in app.engine.livescan (pure); this module
touches the database, the weather/soil services and the photo model.
"""

from __future__ import annotations

import copy
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.engine import advisory as advisory_engine
from app.engine import fieldnow, risk, vision
from app.engine.livescan import LiveSession
from app.kb import KB, tr, trl
from app.models import Diagnosis, Farm, LiveScan, Problem, SensorReading

FAR_FROM_FARM_KM = 2.0  # GPS further than this from the registered farm is flagged


# --------------------------------------------------------------------------
# Context: where, weather now, soil, crop stage, risk from the forecast
# --------------------------------------------------------------------------

def soil_ph_for(db: Session, farm: Farm, lat: float, lon: float, lang: str) -> dict | None:
    since = date.today() - timedelta(days=14)
    sensor = db.scalars(select(SensorReading).where(
        SensorReading.farm_id == farm.id, SensorReading.soil_ph.is_not(None), SensorReading.on >= since,
    ).order_by(SensorReading.on.desc())).first()
    if sensor:
        return {"value": sensor.soil_ph, "how": "measured", "source": "your field sensor",
                "on": sensor.on.isoformat(), "band": fieldnow.ph_band(sensor.soil_ph, lang)}
    if farm.soil_ph:
        return {"value": farm.soil_ph, "how": "card", "source": "your Soil Health Card",
                "on": farm.soil_ph_on.isoformat() if farm.soil_ph_on else None,
                "band": fieldnow.ph_band(farm.soil_ph, lang)}
    sg = fieldnow.soilgrids(lat, lon)
    if sg and sg.get("ph"):
        return {"value": sg["ph"], "how": "estimated", "source": sg["source"], "on": None,
                "band": fieldnow.ph_band(sg["ph"], lang), "soc_g_per_kg": sg.get("soc_g_per_kg")}
    return None


def soil_moisture_for(db: Session, farm: Farm, modelled: dict | None) -> dict | None:
    recent = db.scalars(select(SensorReading).where(
        SensorReading.farm_id == farm.id, SensorReading.soil_moisture_pct.is_not(None),
        SensorReading.on >= date.today() - timedelta(days=2),
    ).order_by(SensorReading.on.desc())).first()
    if recent:
        return {"value_pct": recent.soil_moisture_pct, "how": "measured", "source": "your field sensor",
                "on": recent.on.isoformat()}
    if modelled and modelled.get("moisture_pct_surface") is not None:
        return {"value_pct": modelled["moisture_pct_surface"], "deeper_pct": modelled.get("moisture_pct_3_9cm"),
                "temp_c": modelled.get("temp_c_surface"), "how": "estimated", "source": modelled["source"]}
    return None


def prevention_for(kb: KB, target: str, lang: str) -> dict:
    adv = advisory_engine.compose(kb, target, lang)
    return {
        "avoid": adv["what_to_avoid"][:1],
        "do": [r["action"] for r in adv["ladder"] if r["tier"] != "chemical"][:2],
        "icar": [o["short"] for o in adv["icar_options"]][:2],
    }


def risk_view(kb: KB, r: dict, lang: str) -> dict:
    """One forecast risk in `lang`, from its stored form (target, level, trigger,
    the reason in every language)."""
    t = r["target"]
    return {"target": t, "name": tr(kb.targets[t]["names"], lang), "level": r["level"], "trigger": r["trigger"],
            "reason": risk.reason_text(r.get("reason_i18n"), lang), "reason_i18n": r.get("reason_i18n") or {},
            "check": trl(kb.rules[t]["tasks"], lang)[:2], "prevention": prevention_for(kb, t, lang)}


def context(db: Session, kb: KB, farm: Farm, lat: float | None, lon: float | None,
            accuracy_m: float | None, lang: str) -> dict:
    gps = lat is not None and lon is not None
    lat, lon = (lat, lon) if gps else (farm.lat, farm.lon)
    dist = services.haversine_km(lat, lon, farm.lat, farm.lon) if gps else 0.0
    now = fieldnow.conditions_now(lat, lon, lang)
    window = services.weather_for(db, farm)
    today = date.today()
    forecast = None
    if window:
        ahead = [d for d in window.days if d.on > today][:3]
        if ahead:
            forecast = {
                "days": len(ahead),
                "rain_mm": round(sum(d.rain_mm or 0 for d in ahead), 1),
                "rh_max": max((d.rh_max for d in ahead if d.rh_max is not None), default=None),
                "t_min": min((d.t_min for d in ahead if d.t_min is not None), default=None),
                "t_max": max((d.t_max for d in ahead if d.t_max is not None), default=None),
                "source": window.source,
            }
    risks = []
    for s in services.risk_scores(db, kb, farm, today, window):
        risks.append(risk_view(kb, {"target": s.target, "level": s.level, "trigger": s.trigger,
                                    "reason_i18n": s.reason}, lang))
    stage, das = kb.stage_for(farm.crop, farm.sowing_date, today)
    return {
        "location": {"lat": round(lat, 5), "lon": round(lon, 5), "source": "gps" if gps else "farm",
                     "accuracy_m": accuracy_m, "km_from_farm": round(dist, 2),
                     "far_from_farm": gps and dist > FAR_FROM_FARM_KM},
        "weather_now": now["weather"],
        "forecast": forecast,
        "soil": {"ph": soil_ph_for(db, farm, lat, lon, lang), "moisture": soil_moisture_for(db, farm, now["soil_model"])},
        "crop": {"id": farm.crop, "name": tr(kb.crops[farm.crop]["names"], lang), "stage": stage,
                 "stage_name": kb.stage_name(farm.crop, stage, lang), "das": das,
                 "photo_model": kb.crops[farm.crop]["photo_diagnosis"] and not vision.model_status()["is_stub"]},
        "risks": risks,
    }


# --------------------------------------------------------------------------
# The walk itself
# --------------------------------------------------------------------------

def _namer(kb: KB, lang: str):
    def name(t: str) -> str:
        if t in kb.targets:
            return tr(kb.targets[t]["names"], lang)
        crop = t.split("_")[0]
        if t.endswith("_healthy") and crop in kb.crops:
            return tr(services.HEALTHY_NAME, lang).format(
                crop=tr(kb.crops[crop]["names"], lang))
        return t.replace("_", " ")

    return name


def new_session(kb: KB, farm: Farm, lang: str) -> LiveSession:
    can = kb.crops[farm.crop]["photo_diagnosis"] and not vision.model_status()["is_stub"]
    return LiveSession(crop=farm.crop, lang=lang, can_classify=can, target_name=_namer(kb, lang))


def relang(kb: KB, sess: LiveSession, lang: str) -> None:
    """The farmer switched language mid-call: guidance from now on is in `lang`."""
    sess.lang = lang
    sess.target_name = _namer(kb, lang)


def classify(img) -> list[tuple[str, float]]:
    """Top-3 targets for one close-up, calibrated — the same model as the photo path."""
    model = vision._real_model()
    preds, _, fam = model.analyse(img, with_heatmap=False)
    return preds if model.is_familiar(fam) else []  # not a crop view: nothing to record


MIN_HEALTHY_VIEWS = 2
"""Separate close-ups the model must be sure are healthy before the walk may
say so — the same two-view bar a disease must clear before it is reported as
seen. Absence of a disease in what the camera caught is not health."""


def walk_verdict(seen: bool, possible: bool, can_classify: bool, healthy_confident: int, risks: bool) -> str:
    """What the walk may honestly claim about the plants.

      found         a problem seen in at least two confident close-ups
      check         glimpsed, or photos sent: an expert looks
      no_model      this crop cannot be judged from the camera yet (cotton,
                    soybean) — never reported as healthy
      unclear       the camera did not get enough confident views of the plant
                    to say anything: the farmer is asked to try again
      risk          healthy in what was seen, but the weather favours a problem
      all_good      healthy in what was seen, and no weather risk

    Before this, a walk in which the model recognised nothing fell through to
    "healthy" — "Healthy now, but watch out" after showing the camera nothing."""
    if seen:
        return "found"
    if possible:
        return "check"
    if not can_classify:
        return "no_model"
    if healthy_confident < MIN_HEALTHY_VIEWS:
        return "unclear"
    return "risk" if risks else "all_good"


def finish(db: Session, kb: KB, farm: Farm, sess: LiveSession, ctx: dict, lang: str,
           send_to_expert: bool = False) -> dict:
    f = sess.findings(kb)
    model_version = vision.model_status()["model_version"] if sess.can_classify else "none"
    problem_ids: list[int] = []
    seen_out, possible_out = [], []

    for item in f["seen"]:
        t = item["target"]
        problem = Problem(farm_id=farm.id)
        db.add(problem)
        db.flush()
        frames = sess.evidence_for(t)
        for i, jpeg in enumerate(frames or [None]):
            db.add(Diagnosis(
                problem_id=problem.id, image_path=services.save_upload(jpeg) if jpeg else None,
                topk=[{"target": t, "confidence": item["confidence"]}],
                gate_outcome="advise", gate_reason="LIVE_MULTI_VIEW", confidence=item["confidence"],
                model_version=model_version, is_stub=False,
            ))
        adv = services._advise(db, kb, problem, t, "model", lang, farm)
        problem_ids.append(problem.id)
        seen_out.append(item | {
            "name": tr(kb.targets[t]["names"], lang), "problem_id": problem.id,
            "evidence": [services._image_url(d.image_path) for d in problem.diagnoses if d.image_path],
            "advisory": adv["advisory"], "followup": adv["followup"],
        })

    for item in f["possible"]:
        t = item["target"]
        problem = Problem(farm_id=farm.id)
        db.add(problem)
        db.flush()
        for jpeg in sess.evidence_for(t) or [None]:
            db.add(Diagnosis(
                problem_id=problem.id, image_path=services.save_upload(jpeg) if jpeg else None,
                topk=[{"target": t, "confidence": item["confidence"]}], gate_outcome="escalate",
                gate_reason="LIVE_FEW_VIEWS" if item["reason"] in ("FEW_VIEWS", "MINORITY_VIEWS", "LOOKALIKE") else "NOT_PHOTO_DIAGNOSABLE",
                confidence=item["confidence"], model_version=model_version, is_stub=False,
            ))
        case = services.escalate(db, problem, "LIVE_FEW_VIEWS" if item["reason"] in ("FEW_VIEWS", "MINORITY_VIEWS", "LOOKALIKE")
                                 else "NOT_PHOTO_DIAGNOSABLE")
        problem_ids.append(problem.id)
        possible_out.append(item | {"name": tr(kb.targets[t]["names"], lang), "problem_id": problem.id,
                                    "case": services.case_brief(db, case)})

    expert_case = None
    if send_to_expert and sess.closeups and not seen_out and not possible_out:
        problem = Problem(farm_id=farm.id)
        db.add(problem)
        db.flush()
        for _, jpeg in sess.closeups:
            db.add(Diagnosis(problem_id=problem.id, image_path=services.save_upload(jpeg), topk=[],
                             gate_outcome="escalate", gate_reason="FARMER_REQUEST", confidence=0.0,
                             model_version=model_version, is_stub=False))
        reason = "CROP_NOT_SUPPORTED" if not sess.can_classify else "FARMER_REQUEST"
        expert_case = services.case_brief(db, services.escalate(db, problem, reason))
        problem_ids.append(problem.id)

    verdict = walk_verdict(bool(seen_out), bool(possible_out or expert_case), sess.can_classify,
                           f.get("healthy_confident_views", 0), bool(ctx["risks"]))
    scan = LiveScan(
        farm_id=farm.id, lat=ctx["location"]["lat"], lon=ctx["location"]["lon"],
        location_source=ctx["location"]["source"], frames=f["frames"], good_frames=f["good_frames"],
        classified_views=f["classified_views"], verdict=verdict,
        findings={"seen": [{k: v for k, v in x.items() if k not in ("advisory",)} for x in seen_out],
                  "possible": possible_out, "healthy_views": f["healthy_views"],
                  "other_crop_views": f["other_crop_views"], "answer": f["answer"]},
        context={k: ctx[k] for k in ("location", "weather_now", "forecast", "soil", "crop")}
        | {"risks": [{k: r[k] for k in ("target", "level", "trigger", "reason_i18n")} for r in ctx["risks"]]},
        problem_ids=problem_ids, model_version=model_version,
    )
    db.add(scan)
    db.commit()
    summary = {
        "scan_id": scan.id, "verdict": verdict, "context": ctx,
        "seen": seen_out, "possible": possible_out, "expert_case": expert_case,
        "stats": {"frames": f["frames"], "good_frames": f["good_frames"],
                  "classified_views": f["classified_views"], "healthy_views": f["healthy_views"],
                  "other_crop_views": f["other_crop_views"]},
        "model_version": model_version, "photo_model": sess.can_classify,
    }
    summary["speech"] = speech(summary, lang)
    return summary


def localize_context(kb: KB, context: dict, lang: str) -> dict:
    """The walk's context (weather now, soil, crop, risks) in `lang`, from the
    stored numbers and codes."""
    ctx = copy.deepcopy(context)
    if ctx.get("weather_now"):
        ctx["weather_now"]["text"] = fieldnow.weather_text(ctx["weather_now"], lang)
    ph = (ctx.get("soil") or {}).get("ph")
    if ph and ph.get("value") is not None:
        ph["band"] = fieldnow.ph_band(ph["value"], lang)
    crop = ctx["crop"]
    crop["name"] = tr(kb.crops[crop["id"]]["names"], lang)
    crop["stage_name"] = kb.stage_name(crop["id"], crop["stage"], lang)
    ctx["risks"] = [risk_view(kb, r, lang) for r in ctx.get("risks", []) if r["target"] in kb.targets]
    return ctx


def render(db: Session, kb: KB, farm: Farm, scan: LiveScan, lang: str) -> dict:
    """A finished walk's summary again, in another language — the farmer
    switched language on the summary screen. Built from what was stored; no
    new weather call, nothing re-diagnosed."""
    ctx = localize_context(kb, scan.context, lang)
    f = scan.findings or {}
    views = {p["id"]: p for p in services.problem_views(
        db, kb, [p for p in (db.get(Problem, i) for i in scan.problem_ids or []) if p], lang)}
    seen = []
    for x in f.get("seen", []):
        pv = views.get(x.get("problem_id")) or {}
        seen.append(x | {"name": tr(kb.targets[x["target"]]["names"], lang), "advisory": pv.get("advisory"),
                         "followup": pv.get("followup")})
    possible = [x | {"name": tr(kb.targets[x["target"]]["names"], lang)} for x in f.get("possible", [])]
    expert_case = next((views[i]["case"] for i in scan.problem_ids or []
                        if i in views and views[i]["case"] and not views[i]["target"]), None)
    summary = {
        "scan_id": scan.id, "verdict": scan.verdict, "context": ctx, "seen": seen, "possible": possible,
        "expert_case": expert_case,
        "stats": {"frames": scan.frames, "good_frames": scan.good_frames, "classified_views": scan.classified_views,
                  "healthy_views": f.get("healthy_views", 0), "other_crop_views": f.get("other_crop_views", 0)},
        "model_version": scan.model_version, "photo_model": scan.model_version != "none",
    }
    summary["speech"] = speech(summary, lang)
    return summary


# --------------------------------------------------------------------------
# What the AI says at the end
# --------------------------------------------------------------------------

S = {
    "intro": {"en": "Here is what I found.", "hi": "मैंने जो देखा, वह यह है।", "mr": "मी जे पाहिले ते असे."},
    "weather": {"en": "Right now it is {t} degrees with {rh} percent humidity{txt}.",
                "hi": "अभी तापमान {t} डिग्री और नमी {rh} प्रतिशत है{txt}।",
                "mr": "आत्ता तापमान {t} अंश आणि आर्द्रता {rh} टक्के आहे{txt}."},
    "ph": {"en": "Soil pH is about {v}, {band}, {how}.", "hi": "मिट्टी का पीएच लगभग {v} है, {band}, {how}।",
           "mr": "मातीचा सामू सुमारे {v} आहे, {band}, {how}."},
    "how_measured": {"en": "measured by your sensor", "hi": "आपके सेंसर से मापा गया", "mr": "तुमच्या सेन्सरने मोजलेला"},
    "how_card": {"en": "from your Soil Health Card", "hi": "आपके मृदा स्वास्थ्य कार्ड से", "mr": "तुमच्या मृदा आरोग्य पत्रिकेतून"},
    "how_estimated": {"en": "estimated from the soil map, not measured in your field",
                      "hi": "मिट्टी के नक्शे से अनुमान, आपके खेत में मापा नहीं गया",
                      "mr": "माती नकाशावरून अंदाज, तुमच्या शेतात मोजलेला नाही"},
    "stage": {"en": "Your {crop} is at the {stage} stage, day {das}.",
              "hi": "आपकी {crop} फसल {stage} अवस्था में है, {das}वाँ दिन।",
              "mr": "तुमचे {crop} पीक {stage} अवस्थेत आहे, {das}वा दिवस."},
    "seen": {"en": "I could see {name} on {n} leaves.", "hi": "मुझे {n} पत्तियों पर {name} दिखा।",
             "mr": "मला {n} पानांवर {name} दिसले."},
    "avoid": {"en": "Important: {x}", "hi": "ज़रूरी: {x}", "mr": "महत्त्वाचे: {x}"},
    "first": {"en": "First do this: {x}", "hi": "पहले यह करें: {x}", "mr": "आधी हे करा: {x}"},
    "possible": {"en": "I may have seen {names}, but not clearly enough to be sure. An expert will look at the photos.",
                 "hi": "शायद {names} दिखा, पर पक्का कहने लायक साफ़ नहीं। विशेषज्ञ फोटो देखेंगे।",
                 "mr": "कदाचित {names} दिसले, पण खात्रीने सांगण्याइतके स्पष्ट नाही. तज्ज्ञ फोटो पाहतील."},
    "unclear": {"en": "I could not see your plants clearly enough to tell whether they are healthy. "
                      "Please try again: hold the phone close to a leaf, in daylight, and keep it still.",
                "hi": "मैं आपके पौधे इतने साफ़ नहीं देख पाया कि बता सकूँ कि वे स्वस्थ हैं या नहीं। "
                      "कृपया फिर से कोशिश करें: फ़ोन को पत्ती के पास, दिन की रोशनी में, स्थिर रखें।",
                "mr": "तुमची रोपे निरोगी आहेत की नाही हे सांगण्याइतकी स्पष्ट दिसली नाहीत. "
                      "कृपया पुन्हा प्रयत्न करा: फोन पानाजवळ, दिवसाच्या उजेडात, स्थिर धरा."},
    "healthy": {"en": "All the plants I saw look healthy.", "hi": "जितने पौधे मैंने देखे, सब स्वस्थ दिखते हैं।",
                "mr": "मी पाहिलेली सर्व रोपे निरोगी दिसतात."},
    "no_model": {"en": "I can't judge {crop} diseases from the camera yet.",
                 "hi": "मैं अभी कैमरे से {crop} के रोग नहीं पहचान सकता।",
                 "mr": "मी अजून कॅमेऱ्यावरून {crop} पिकाचे रोग ओळखू शकत नाही."},
    "expert_sent": {"en": "Your close-up photos have gone to an expert.",
                    "hi": "आपकी पास की फोटो विशेषज्ञ को भेज दी गई हैं।",
                    "mr": "तुमचे जवळचे फोटो तज्ज्ञांकडे पाठवले आहेत."},
    "risk": {"en": "But the weather shows {name} may come: {reason} To prevent it: {x}",
             "hi": "लेकिन मौसम बताता है कि {name} आ सकता है: {reason} बचाव के लिए: {x}",
             "mr": "पण हवामानानुसार {name} येऊ शकतो: {reason} प्रतिबंधासाठी: {x}"},
    "no_risk": {"en": "No weather risk for your crop in the coming days.",
                "hi": "आने वाले दिनों में आपकी फसल के लिए मौसम से कोई खतरा नहीं।",
                "mr": "येत्या दिवसांत तुमच्या पिकाला हवामानामुळे धोका नाही."},
}


def _s(key: str, lang: str, **kw) -> str:
    return tr(S[key], lang).format(**kw)


def speech(summary: dict, lang: str) -> str:
    ctx = summary["context"]
    parts = [_s("intro", lang)]
    w = ctx.get("weather_now")
    if w and w.get("temp_c") is not None:
        txt = f", {w['text']}" if w.get("text") else ""
        parts.append(_s("weather", lang, t=round(w["temp_c"]), rh=round(w["rh_pct"]), txt=txt))
    ph = (ctx.get("soil") or {}).get("ph")
    if ph:
        parts.append(_s("ph", lang, v=ph["value"], band=ph["band"], how=_s(f"how_{ph['how']}", lang)))
    c = ctx["crop"]
    parts.append(_s("stage", lang, crop=c["name"], stage=c["stage_name"], das=c["das"]))
    for x in summary["seen"]:
        parts.append(_s("seen", lang, name=x["name"], n=x["views"]))
        adv = x["advisory"]
        if adv["what_to_avoid"]:
            parts.append(_s("avoid", lang, x=adv["what_to_avoid"][0]))
        first = next((r["action"] for r in adv["ladder"] if r["tier"] != "chemical"), None)
        if first:
            parts.append(_s("first", lang, x=first))
    if summary["possible"]:
        parts.append(_s("possible", lang, names=", ".join(x["name"] for x in summary["possible"])))
    if not summary["seen"] and not summary["possible"]:
        if summary.get("verdict") == "unclear":
            parts.append(_s("unclear", lang))
        elif summary["photo_model"]:
            parts.append(_s("healthy", lang))
        else:
            parts.append(_s("no_model", lang, crop=c["name"]))
    if summary.get("expert_case"):
        parts.append(_s("expert_sent", lang))
    seen_targets = {x["target"] for x in summary["seen"]}
    risks = [r for r in ctx["risks"] if r["target"] not in seen_targets][:2]
    for r in risks:
        step = (r["prevention"]["do"] or r["check"] or [""])[0]
        parts.append(_s("risk", lang, name=r["name"], reason=r["reason"].rstrip(".।") + ".", x=step))
    if not risks:
        parts.append(_s("no_risk", lang))
    return " ".join(p.strip() for p in parts if p)
