"""Orchestration: the engine's pure functions plus the database.

Routers stay thin and call these. Every farmer-facing response is built here
in the requested language, so the three screens (farmer, expert, officials)
see the same facts.
"""

from __future__ import annotations

import calendar
import io
import json
import math
import uuid
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.i18n import month_name as i18n_month
from app.config import (
    CASE_ETA_MINUTES_PER_POSITION,
    FOLLOWUP_DUE_DAYS,
    KB_DIR,
    MAX_RISK_ALERTS_PER_FARM_PER_DAY,
    SATELLITE_MAX_AGE_DAYS,
    SPREAD_RADIUS_KM,
    UPLOAD_DIR,
)
from app.engine import advisory as advisory_engine
from app.engine import assign, doubt, gate, prior, risk, vision
from app.engine.weather import WeatherUnavailable, fetch_month_rain, fetch_window, merge_rain, merge_sensor
from app.kb import KB, tr, trl
from app.models import (
    Advisory,
    Alert,
    Case,
    Confirmation,
    Diagnosis,
    ExpertProfile,
    Farm,
    FollowUp,
    LabelPrior,
    Observation,
    Problem,
    SensorReading,
    TrapReading,
    User,
)

HEALTHY_NAME = {"en": "Healthy {crop}", "hi": "स्वस्थ {crop}", "mr": "निरोगी {crop}"}

MESSAGES = {
    "ABOVE_GATE": {"en": "", "hi": "", "mr": ""},
    "HEALTHY": {"en": "", "hi": "", "mr": ""},
    "AMBIGUOUS": {
        "en": "I see two possibilities. One quick check in your field will settle it.",
        "hi": "मुझे दो संभावनाएँ दिख रही हैं। खेत में एक छोटी जाँच से पता चल जाएगा।",
        "mr": "मला दोन शक्यता दिसत आहेत. शेतातील एका छोट्या तपासणीने खात्री होईल.",
    },
    "BELOW_FLOOR": {
        "en": "I am not sure what this is, so I will not guess. An expert will look at your photo.",
        "hi": "मुझे पक्का नहीं पता कि यह क्या है, इसलिए मैं अंदाज़ा नहीं लगाऊँगा। विशेषज्ञ आपकी फोटो देखेंगे।",
        "mr": "हे काय आहे याची मला खात्री नाही, म्हणून मी अंदाज लावणार नाही. तज्ज्ञ तुमचा फोटो पाहतील.",
    },
    "BELOW_GATE": {
        "en": "I have a likely answer but I am not confident enough to advise spraying. An expert will confirm.",
        "hi": "मेरे पास संभावित उत्तर है, पर छिड़काव की सलाह देने लायक भरोसा नहीं। विशेषज्ञ पुष्टि करेंगे।",
        "mr": "माझ्याकडे संभाव्य उत्तर आहे, पण फवारणीचा सल्ला देण्याइतकी खात्री नाही. तज्ज्ञ खात्री करतील.",
    },
    "LAB_CLASS_CONFIRM": {
        "en": "This looks like a disease I learnt from lab photos, so I want one quick check in your field before advising.",
        "hi": "यह ऐसा रोग लगता है जो मैंने प्रयोगशाला की फोटो से सीखा है, इसलिए सलाह से पहले खेत में एक छोटी जाँच चाहिए।",
        "mr": "हा रोग मी प्रयोगशाळेतील फोटोंवरून शिकलो आहे, म्हणून सल्ल्यापूर्वी शेतात एक छोटी तपासणी हवी.",
    },
    "LAB_CLASS_BELOW_GATE": {
        "en": "This may be a disease I learnt from lab photos, and I am not sure enough on a field photo. An expert will confirm.",
        "hi": "यह ऐसा रोग हो सकता है जो मैंने प्रयोगशाला की फोटो से सीखा है; खेत की फोटो पर मुझे पूरा भरोसा नहीं। विशेषज्ञ पुष्टि करेंगे।",
        "mr": "हा रोग मी प्रयोगशाळेतील फोटोंवरून शिकलो असू शकतो; शेतातील फोटोवर पुरेशी खात्री नाही. तज्ज्ञ खात्री करतील.",
    },
    "AMBIGUOUS_NO_CUE": {
        "en": "I see two possibilities and no simple field check separates them. An expert will look.",
        "hi": "दो संभावनाएँ हैं और कोई आसान जाँच इन्हें अलग नहीं करती। विशेषज्ञ देखेंगे।",
        "mr": "दोन शक्यता आहेत आणि कोणतीही सोपी तपासणी त्या वेगळ्या करत नाही. तज्ज्ञ पाहतील.",
    },
    "ANSWER_DID_NOT_DISCRIMINATE": {
        "en": "That's all right — I won't guess. An expert will look at your photo and your answer.",
        "hi": "कोई बात नहीं — मैं अंदाज़ा नहीं लगाऊँगा। विशेषज्ञ आपकी फोटो और उत्तर देखेंगे।",
        "mr": "हरकत नाही — मी अंदाज लावणार नाही. तज्ज्ञ तुमचा फोटो व उत्तर पाहतील.",
    },
    "NOT_A_CROP_PHOTO": {
        "en": "This does not look like a crop photo. Photograph the affected leaf up close, in daylight.",
        "hi": "यह फसल की फोटो नहीं लगती। प्रभावित पत्ती की पास से, दिन की रोशनी में फोटो लें।",
        "mr": "हा पिकाचा फोटो वाटत नाही. बाधित पानाचा जवळून, दिवसाच्या उजेडात फोटो घ्या.",
    },
    "UNFAMILIAR_PHOTO": {
        "en": "This is a crop photo, but not like the ones I have been taught on, so I will not guess. An expert will look at it.",
        "hi": "यह फसल की फोटो है, पर जिन फोटो पर मैंने सीखा है उनसे अलग है, इसलिए मैं अंदाज़ा नहीं लगाऊँगा। विशेषज्ञ इसे देखेंगे।",
        "mr": "हा पिकाचा फोटो आहे, पण मी ज्या फोटोंवरून शिकलो त्यांच्यासारखा नाही, म्हणून मी अंदाज लावणार नाही. तज्ज्ञ तो पाहतील.",
    },
    "CROP_MISMATCH": {
        "en": "This photo does not match the crop registered for your field. An expert will check it.",
        "hi": "यह फोटो आपके खेत की दर्ज फसल से मेल नहीं खाती। विशेषज्ञ जाँच करेंगे।",
        "mr": "हा फोटो तुमच्या शेतातील नोंदवलेल्या पिकाशी जुळत नाही. तज्ज्ञ तपासतील.",
    },
    "NOT_PHOTO_DIAGNOSABLE": {
        "en": "This problem can't be confirmed from a photo alone. An expert will guide you on what to check.",
        "hi": "यह समस्या केवल फोटो से पक्की नहीं हो सकती। विशेषज्ञ बताएँगे क्या जाँचें।",
        "mr": "ही समस्या फक्त फोटोवरून निश्चित होऊ शकत नाही. काय तपासायचे ते तज्ज्ञ सांगतील.",
    },
    "NO_KB_ENTRY": {
        "en": "I have no verified advice for this yet. An expert will guide you.",
        "hi": "इसके लिए मेरे पास अभी प्रमाणित सलाह नहीं है। विशेषज्ञ मार्गदर्शन करेंगे।",
        "mr": "यासाठी माझ्याकडे अद्याप प्रमाणित सल्ला नाही. तज्ज्ञ मार्गदर्शन करतील.",
    },
    "CROP_NOT_SUPPORTED": {
        "en": "Photo diagnosis for this crop isn't available yet. Your photo goes to an expert; your alerts tell you what to check.",
        "hi": "इस फसल के लिए फोटो निदान अभी उपलब्ध नहीं है। आपकी फोटो विशेषज्ञ को जाएगी; अलर्ट बताएँगे क्या जाँचें।",
        "mr": "या पिकासाठी फोटो निदान अद्याप उपलब्ध नाही. तुमचा फोटो तज्ज्ञांकडे जाईल; सूचना काय तपासायचे ते सांगतील.",
    },
    "FARMER_REQUEST": {
        "en": "Your case has been sent to an expert.",
        "hi": "आपका मामला विशेषज्ञ को भेज दिया गया है।",
        "mr": "तुमचे प्रकरण तज्ज्ञांकडे पाठवले आहे.",
    },
    "FOLLOWUP_WORSE": {
        "en": "Sorry it got worse. An expert will look at your case today.",
        "hi": "खेद है कि हालत बिगड़ी। विशेषज्ञ आज आपका मामला देखेंगे।",
        "mr": "परिस्थिती बिघडल्याबद्दल क्षमस्व. तज्ज्ञ आज तुमचे प्रकरण पाहतील.",
    },
    "LIVE_FEW_VIEWS": {
        "en": "Seen in the live check, but not in enough views to be sure. An expert will look at the photos.",
        "hi": "लाइव जाँच में दिखा, पर पक्का होने लायक दृश्यों में नहीं। विशेषज्ञ फोटो देखेंगे।",
        "mr": "थेट तपासणीत दिसले, पण खात्रीसाठी पुरेशा दृश्यांत नाही. तज्ज्ञ फोटो पाहतील.",
    },
    "INSPECTION_FOUND": {
        "en": "Thanks for checking. An expert will confirm what you found.",
        "hi": "जाँच के लिए धन्यवाद। विशेषज्ञ आपकी जाँच की पुष्टि करेंगे।",
        "mr": "तपासणीबद्दल धन्यवाद. तुम्हाला आढळलेल्याची तज्ज्ञ खात्री करतील.",
    },
}


def msg(code: str, lang: str) -> str:
    return tr(MESSAGES.get(code), lang)


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------


def farm_view(kb: KB, farm: Farm, lang: str, today: date | None = None) -> dict:
    stage, das = kb.stage_of(farm, today)
    return {
        "id": farm.id,
        "farmer_name": farm.farmer_name,
        "crop": farm.crop,
        "crop_name": tr(kb.crops[farm.crop]["names"], lang),
        "photo_diagnosis": kb.crops[farm.crop]["photo_diagnosis"],
        "variety": farm.variety,
        "state": farm.state,
        "district": farm.district,
        "village": farm.village,
        "lat": farm.lat,
        "lon": farm.lon,
        "location_source": farm.location_source or "district",
        "area_acres": farm.area_acres,
        "sowing_date": farm.sowing_date.isoformat(),
        "date_basis": farm.date_basis,
        "stage": stage,
        "stage_name": kb.stage_name(farm.crop, stage, lang),
        "das": das,
        "lang": farm.lang,
        "is_demo": farm.is_demo,
    }


def _pred_view(kb: KB, p: gate.Prediction, lang: str) -> dict:
    crop = gate.crop_of(p.target)
    if p.target in kb.targets:
        v = kb.target_view(p.target, lang)
    elif gate.is_healthy(p.target) and crop in kb.crops:
        name = tr(HEALTHY_NAME, lang).format(crop=tr(kb.crops[crop]["names"], lang))
        v = {"id": p.target, "name": name, "signature": "", "crop": crop}
    else:
        v = {"id": p.target, "name": p.target.replace("_", " "), "signature": "", "crop": gate.crop_of(p.target)}
    return v | {"confidence": round(p.confidence, 4)}


def alert_view(kb: KB, a: Alert, lang: str) -> dict:
    t = kb.targets[a.target]
    return {
        "id": a.id,
        "farm_id": a.farm_id,
        "target": a.target,
        "name": tr(t["names"], lang),
        "crop": t["crop"],
        "tier": t["tier"],
        "trigger": a.trigger,
        "level": a.level,
        "reason": risk.reason_text(a.reason, lang),
        "tasks": trl(a.tasks, lang),
        "issued_on": a.issued_on.isoformat(),
        "outcome": a.outcome,
        "can_photo": t["tier"] == "diagnosable" and kb.crops[t["crop"]]["photo_diagnosis"],
    }


def _image_url(path: str | None) -> str | None:
    return f"/media/{path}" if path else None


# --------------------------------------------------------------------------
# Diagnosis
# --------------------------------------------------------------------------


def save_upload(image_bytes: bytes) -> str:
    img = vision.open_image(image_bytes)
    img.thumbnail((1280, 1280))
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    (UPLOAD_DIR / name).write_bytes(buf.getvalue())
    return name


def prior_counts(db: Session, district: str, crop: str) -> dict[str, tuple[int, int]]:
    rows = db.scalars(
        select(LabelPrior).where(LabelPrior.district == district, LabelPrior.crop == crop)
    ).all()
    return {r.target: (r.confirmed, r.corrected) for r in rows}


def _queue_position(db: Session, case: Case) -> int:
    ahead = db.scalar(
        select(func.count(Case.id)).where(Case.status == "open", Case.id < case.id)
    )
    return (ahead or 0) + 1


def case_briefs(db: Session, cases: list[Case]) -> dict[int, dict]:
    """Briefs for a whole queue in three queries instead of three per case.

    The production database is remote, so an N+1 here is not a few microseconds
    — it is a round trip each, and the queue took seconds to open."""
    if not cases:
        return {}
    open_ids = [i for (i,) in db.execute(
        select(Case.id).where(Case.status == "open").order_by(Case.id)).all()]
    position = {cid: n + 1 for n, cid in enumerate(open_ids)}
    officer_ids = {c.assigned_to for c in cases if c.assigned_to}
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_(officer_ids))).all()) if officer_ids else {}
    out = {}
    for c in cases:
        pos = position.get(c.id, 0) if c.status == "open" else 0
        out[c.id] = {
            "id": c.id, "status": c.status, "reason": c.reason,
            "queue_position": pos, "eta_minutes": pos * CASE_ETA_MINUTES_PER_POSITION,
            "assigned_to": c.assigned_to, "assigned_name": names.get(c.assigned_to),
        }
    return out


def case_brief(db: Session, case: Case) -> dict:
    pos = _queue_position(db, case) if case.status == "open" else 0
    officer = db.get(User, case.assigned_to) if case.assigned_to else None
    return {
        "id": case.id,
        "status": case.status,
        "reason": case.reason,
        "queue_position": pos,
        "eta_minutes": pos * CASE_ETA_MINUTES_PER_POSITION,
        "assigned_to": case.assigned_to,
        "assigned_name": officer.name if officer else None,
    }


def officers_for(db: Session, district: str | None, demo: bool = False) -> list[assign.Candidate]:
    """Verified officers who cover this district, with the load each is carrying.

    Demo and real never mix: a showcase farm's case goes to a demo officer, and
    a farmer who signed up for their own field is never reviewed by whoever
    tapped "try the demo". Nobody covering the district? Fall back to every
    officer on the same side of that line, so a case is never stranded."""
    rows = db.execute(
        select(User.id, ExpertProfile.districts)
        .join(ExpertProfile, ExpertProfile.user_id == User.id)
        .where(User.role == "expert", ExpertProfile.verified.is_(True),
               User.is_demo.is_(demo))
    ).all()
    covering = [uid for uid, districts in rows if district and district in (districts or [])]
    user_ids = covering or [uid for uid, _ in rows]
    if not user_ids:
        return []

    open_counts = dict(db.execute(
        select(Case.assigned_to, func.count(Case.id))
        .where(Case.assigned_to.in_(user_ids), Case.status == "open")
        .group_by(Case.assigned_to)
    ).all())
    # Last activity: the most recent case they were handed or finished.
    last_active = dict(db.execute(
        select(Case.assigned_to, func.max(func.coalesce(Case.resolved_at, Case.assigned_at)))
        .where(Case.assigned_to.in_(user_ids))
        .group_by(Case.assigned_to)
    ).all())
    return [assign.Candidate(uid, open_counts.get(uid, 0), last_active.get(uid)) for uid in user_ids]


def case_is_visible_to(db: Session, case: Case, user: User | None) -> bool:
    """A demo account sees demo farms; a real account sees real ones. Checked on
    every case route, not only in the list, so an id cannot be guessed across."""
    if user is None:
        return True  # sign-in is off (older flow tests); the routers guard that
    problem = db.get(Problem, case.problem_id)
    return bool(problem and problem.farm.is_demo == user.is_demo)


def workload(db: Session, district: str | None = None, demo: bool = False) -> list[dict]:
    """Every verified officer, what they are holding, and how long the oldest
    case has waited. The district office reads this before it rebalances;
    `district` narrows it to the officers who actually cover one."""
    rows = db.execute(
        select(User.id, User.name, ExpertProfile.districts, ExpertProfile.designation)
        .join(ExpertProfile, ExpertProfile.user_id == User.id)
        .where(User.role == "expert", ExpertProfile.verified.is_(True), User.is_demo.is_(demo))
        .order_by(User.name)
    ).all()
    if district:
        covering = [r for r in rows if district in (r[2] or [])]
        rows = covering or rows  # nobody covers it: show everyone rather than nobody
    if not rows:
        return []
    # Three queries for the whole board, not two per officer: a district can have
    # eighty desks and the database is a network hop away.
    ids = [r[0] for r in rows]
    # Only cases from this side of the demo line count towards a desk's load.
    on_side = (select(Case.assigned_to, Case.status, Case.created_at, Case.id)
               .join(Problem, Problem.id == Case.problem_id)
               .join(Farm, Farm.id == Problem.farm_id)
               .where(Case.assigned_to.in_(ids), Farm.is_demo.is_(demo))).subquery()
    counts = {
        (uid, status): n
        for uid, status, n in db.execute(
            select(on_side.c.assigned_to, on_side.c.status, func.count(on_side.c.id))
            .group_by(on_side.c.assigned_to, on_side.c.status)
        ).all()
    }
    oldest = dict(db.execute(
        select(on_side.c.assigned_to, func.min(on_side.c.created_at))
        .where(on_side.c.status == "open")
        .group_by(on_side.c.assigned_to)
    ).all())
    now = datetime.now()
    out = []
    for uid, name, districts, designation in rows:
        first = oldest.get(uid)
        out.append({
            "user_id": uid, "name": name, "designation": designation,
            "districts": districts or [],
            "open_cases": counts.get((uid, "open"), 0),
            "resolved_cases": counts.get((uid, "resolved"), 0),
            "oldest_wait_hours": round((now - first).total_seconds() / 3600, 1) if first else None,
        })
    return out


def route_unassigned(db: Session, demo: bool = False) -> dict:
    """Hand every unplaced open case to an officer. What the district office
    presses after verifying new officers, or when a backlog built up while
    nobody covered a district."""
    cases = db.scalars(
        select(Case).join(Problem, Problem.id == Case.problem_id)
        .join(Farm, Farm.id == Problem.farm_id)
        .where(Case.status == "open", Case.assigned_to.is_(None), Farm.is_demo.is_(demo))
        .order_by(Case.id)
    ).all()
    placed = 0
    for case in cases:
        problem = db.get(Problem, case.problem_id)
        if problem and assign_case(db, case, problem.farm) is not None:
            placed += 1
    db.commit()
    return {"considered": len(cases), "assigned": placed}


def reassign_case(db: Session, case: Case, to_user_id: int | None) -> int | None:
    """Hand a case to a named officer, or let the router pick the freest one."""
    if to_user_id is not None:
        officer = db.get(User, to_user_id)
        if officer is None or officer.role != "expert":
            raise ValueError("not an officer")
        case.assigned_to = to_user_id
        case.assigned_at = datetime.now()
        db.flush()
        return to_user_id
    problem = db.get(Problem, case.problem_id)
    holder = case.assigned_to
    case.assigned_to = None  # so the router does not count this case against its current holder
    db.flush()
    # Handing a case on means handing it to somebody else; the holder is only
    # eligible again when they are the district's one officer.
    picked = assign_case(db, case, problem.farm, exclude={holder} if holder else set())
    return picked if picked is not None else assign_case(db, case, problem.farm)


def assign_case(db: Session, case: Case, farm: Farm, exclude: set[int] | None = None) -> int | None:
    """Route a case to the officer who can reach it soonest (app.engine.assign)."""
    candidates = [c for c in officers_for(db, farm.district, demo=farm.is_demo)
                  if c.user_id not in (exclude or set())]
    picked = assign.pick(candidates)
    if picked is not None:
        case.assigned_to = picked
        case.assigned_at = datetime.now()
        db.flush()
    return picked


def escalate(db: Session, problem: Problem, reason: str) -> Case:
    existing = db.scalar(select(Case).where(Case.problem_id == problem.id, Case.status == "open"))
    if existing:
        return existing
    case = Case(problem_id=problem.id, reason=reason)
    db.add(case)
    db.flush()
    assign_case(db, case, problem.farm)
    return case


def _schedule_followup(db: Session, problem: Problem, today: date | None = None) -> FollowUp:
    fu = FollowUp(problem_id=problem.id, due_on=(today or date.today()) + timedelta(days=FOLLOWUP_DUE_DAYS))
    db.add(fu)
    db.flush()
    return fu


def _advise(db: Session, kb: KB, problem: Problem, target: str, source: str, lang: str, farm: Farm) -> dict:
    problem.target = target
    db.add(Advisory(problem_id=problem.id, target=target, source=source))
    fu = _schedule_followup(db, problem)
    return {
        "advisory": advisory_engine.compose(kb, target, lang, farm.area_acres),
        "followup": {"id": fu.id, "due_on": fu.due_on.isoformat()},
    }


def diagnose(
    db: Session, kb: KB, farm: Farm, image_bytes: bytes, lang: str, scenario: str | None = None
) -> dict:
    image_path = save_upload(image_bytes)
    problem = Problem(farm_id=farm.id)
    db.add(problem)
    db.flush()

    base = {"problem_id": problem.id, "image_url": _image_url(image_path)}

    if not kb.crops[farm.crop]["photo_diagnosis"]:
        db.add(Diagnosis(
            problem_id=problem.id, image_path=image_path, topk=[], gate_outcome="escalate",
            gate_reason="CROP_NOT_SUPPORTED", confidence=0.0, model_version="none", is_stub=False,
        ))
        case = escalate(db, problem, "CROP_NOT_SUPPORTED")
        db.commit()
        return base | {
            "is_stub": False, "model_version": "none",
            "gate": {"outcome": "escalate", "reason": "CROP_NOT_SUPPORTED", "confidence": 0.0,
                     "threshold": 0.0, "alternatives": []},
            "message": msg("CROP_NOT_SUPPORTED", lang),
            "case": case_brief(db, case),
        }

    raw = vision.classify(image_bytes, farm.crop, scenario)
    topk = prior.apply_prior(raw, prior_counts(db, farm.district, farm.crop))
    decision = gate.decide(
        topk,
        farm_crop=farm.crop,
        tier_of=lambda t: kb.targets.get(t, {}).get("tier"),
        has_advisory=lambda t: t in kb.advisories,
        cue_for=kb.cue_for,
    )
    diag = Diagnosis(
        problem_id=problem.id,
        image_path=image_path,
        topk=[{"target": p.target, "confidence": p.confidence} for p in topk.predictions],
        gate_outcome=decision.outcome,
        gate_reason=decision.reason,
        confidence=decision.confidence,
        model_version=topk.model_version,
        is_stub=topk.is_stub,
        heatmap=topk.heatmap,
    )
    db.add(diag)
    db.flush()

    result = base | {
        "diagnosis_id": diag.id,
        "is_stub": topk.is_stub,
        "model_version": topk.model_version,
        "heatmap": topk.heatmap,
        "prior_bias": topk.prior_bias,
        "gate": {
            "outcome": decision.outcome,
            "reason": decision.reason,
            "confidence": round(decision.confidence, 4),
            "threshold": decision.threshold,
            "alternatives": [_pred_view(kb, p, lang) for p in decision.alternatives],
        },
        "message": msg(decision.reason, lang),
    }

    if decision.outcome == "advise":
        top = decision.alternatives[0].target
        if gate.is_healthy(top):
            problem.target, problem.status, problem.severity = top, "resolved", "low"
            problem.resolved_at = datetime.now(UTC)
            result["healthy_note"] = advisory_engine.healthy_note(lang)
        else:
            result |= _advise(db, kb, problem, top, "model", lang, farm)
    elif decision.outcome == "clarify":
        cue = next(c for c in kb.cues if c["id"] == decision.cue_id)
        a, b = decision.alternatives[0].target, decision.alternatives[1].target
        result["clarify"] = {
            "cue_id": cue["id"],
            "question": tr(cue["question"], lang),
            "candidates": [kb.target_view(a, lang), kb.target_view(b, lang)],
        }
    elif decision.outcome == "escalate":
        case = escalate(db, problem, decision.reason)
        result["case"] = case_brief(db, case)
    else:  # retake
        problem.status = "resolved"
        problem.resolved_at = datetime.now(UTC)

    db.commit()
    return result


def result_view(db: Session, kb: KB, problem: Problem, lang: str) -> dict:
    """A photo check's result again, in `lang` and as things stand now (the
    question answered, or sent to an expert since). Same shape as diagnose()."""
    diag = db.scalars(select(Diagnosis).where(Diagnosis.problem_id == problem.id).order_by(Diagnosis.id)).first()
    if diag is None:
        raise ValueError("no photo check on this problem")
    preds = [gate.Prediction(p["target"], p["confidence"]) for p in diag.topk]
    top = preds[0].target if preds else None
    out = {
        "problem_id": problem.id, "image_url": _image_url(diag.image_path), "diagnosis_id": diag.id,
        "is_stub": diag.is_stub, "model_version": diag.model_version, "heatmap": diag.heatmap,
        "gate": {"outcome": diag.gate_outcome, "reason": diag.gate_reason, "confidence": round(diag.confidence, 4),
                 "threshold": gate.threshold_of(diag.gate_reason, top),
                 "alternatives": [_pred_view(kb, p, lang) for p in preds]},
        "message": msg(diag.gate_reason, lang),
    }
    case = db.scalars(select(Case).where(Case.problem_id == problem.id).order_by(Case.id.desc())).first()
    advisory = db.scalars(select(Advisory).where(Advisory.problem_id == problem.id)
                          .order_by(Advisory.id.desc())).first()
    if case is not None:  # asked for an expert, or the answer didn't settle it
        out["gate"] |= {"outcome": "escalate", "reason": case.reason}
        out |= {"message": msg(case.reason, lang), "case": case_brief(db, case)}
    elif advisory is not None:
        fu = db.scalars(select(FollowUp).where(FollowUp.problem_id == problem.id).order_by(FollowUp.id.desc())).first()
        out["gate"]["outcome"] = "advise"
        out |= {"advisory": advisory_engine.compose(kb, advisory.target, lang, problem.farm.area_acres),
                "followup": {"id": fu.id, "due_on": fu.due_on.isoformat()} if fu else None}
        if advisory.source == "doubt_doctor":
            out["resolved_target"] = advisory.target
    elif diag.gate_outcome == "advise" and top and gate.is_healthy(top):
        out["healthy_note"] = advisory_engine.healthy_note(lang)
    elif diag.gate_outcome == "clarify" and len(preds) > 1:
        cue = kb.cue_for(preds[0].target, preds[1].target)
        if cue:
            out["clarify"] = {"cue_id": cue["id"], "question": tr(cue["question"], lang),
                              "candidates": [kb.target_view(preds[0].target, lang), kb.target_view(preds[1].target, lang)]}
    return out


def answer_clarify(db: Session, kb: KB, problem: Problem, cue_id: str, answer: str, lang: str) -> dict:
    cue = next((c for c in kb.cues if c["id"] == cue_id), None)
    if cue is None:
        raise ValueError(f"unknown cue {cue_id}")
    db.add(Observation(
        problem_id=problem.id, kind="doubt_doctor", cue_id=cue_id,
        question=tr(cue["question"], "en"), answer=answer,
    ))
    resolved = doubt.resolve(cue, answer)
    farm = problem.farm
    if resolved is None:
        case = escalate(db, problem, "ANSWER_DID_NOT_DISCRIMINATE")
        db.commit()
        return {
            "problem_id": problem.id, "outcome": "escalate",
            "message": msg("ANSWER_DID_NOT_DISCRIMINATE", lang), "case": case_brief(db, case),
        }
    out = _advise(db, kb, problem, resolved, "doubt_doctor", lang, farm)
    db.commit()
    return {"problem_id": problem.id, "outcome": "advise", "resolved_target": resolved, **out}


@lru_cache(maxsize=512)
def translate_note(text: str, lang: str) -> tuple[str, bool]:
    """Expert notes are typed in English; the farmer reads them in their own
    language via Sarvam-Translate. Falls back to the original text (flagged)
    rather than failing the whole view when the service is unavailable."""
    if lang == "en" or not text.strip():
        return text, False
    try:
        from app import voice  # noqa: PLC0415

        return voice.translate(text, "en", lang), True
    except Exception:
        return text, False


def _latest(db: Session, model, ids: list[int], *where) -> dict:
    """{problem_id: newest row} for many problems in one query."""
    rows = db.scalars(select(model).where(model.problem_id.in_(ids), *where).order_by(model.id)).all()
    return {r.problem_id: r for r in rows}  # ascending ids: the newest one wins


def problem_views(db: Session, kb: KB, problems: list[Problem], lang: str) -> list[dict]:
    """Views for a list of problems in five queries, not five per problem — the
    database may be a network hop away (Postgres in the cloud)."""
    ids = [p.id for p in problems]
    if not ids:
        return []
    diags = _latest(db, Diagnosis, ids)
    advs = _latest(db, Advisory, ids)
    cases = _latest(db, Case, ids)
    confs = _latest(db, Confirmation, ids)
    fus = _latest(db, FollowUp, ids, FollowUp.response.is_(None))
    return [_problem_view(db, kb, p, lang, diags.get(p.id), advs.get(p.id), cases.get(p.id),
                          confs.get(p.id), fus.get(p.id)) for p in problems]


def problem_view(db: Session, kb: KB, problem: Problem, lang: str) -> dict:
    return problem_views(db, kb, [problem], lang)[0]


def _problem_view(db: Session, kb: KB, problem: Problem, lang: str, last_diag, advisory_row, case, conf, fu) -> dict:
    target = problem.target
    return {
        "id": problem.id,
        "farm_id": problem.farm_id,
        "status": problem.status,
        "severity": problem.severity,
        "opened_at": problem.opened_at.isoformat() if problem.opened_at else None,
        "target": target,
        "name": tr(kb.targets[target]["names"], lang) if target in kb.targets else None,
        "image_url": _image_url(last_diag.image_path) if last_diag else None,
        "gate_outcome": last_diag.gate_outcome if last_diag else None,
        "gate_reason": last_diag.gate_reason if last_diag else None,
        "confidence": last_diag.confidence if last_diag else None,
        "is_stub": last_diag.is_stub if last_diag else None,
        "advisory_source": advisory_row.source if advisory_row else None,
        "advisory": advisory_engine.compose(kb, advisory_row.target, lang, problem.farm.area_acres)
        if advisory_row else None,
        "case": case_brief(db, case) if case else None,
        "expert": {
            "verdict": conf.verdict, "final_label": conf.final_label, "expert_name": conf.expert_name,
            "notes": translate_note(conf.notes, lang)[0] if conf.notes else None,
            "notes_translated": translate_note(conf.notes, lang)[1] if conf.notes else False,
            "referred_to_lab": conf.referred_to_lab,
        } if conf else None,
        "followup": {"id": fu.id, "due_on": fu.due_on.isoformat(),
                     "due": fu.due_on <= date.today()} if fu else None,
    }


def respond_followup(db: Session, kb: KB, fu: FollowUp, response: str, lang: str) -> dict:
    fu.response = response
    fu.responded_at = datetime.now(UTC)
    problem = db.get(Problem, fu.problem_id)
    out: dict = {"followup_id": fu.id, "response": response}
    if response == "improved":
        problem.status, problem.resolved_at = "resolved", datetime.now(UTC)
    elif response == "got_worse":
        problem.severity = "high"
        case = escalate(db, problem, "FOLLOWUP_WORSE")
        out |= {"case": case_brief(db, case), "message": msg("FOLLOWUP_WORSE", lang)}
    else:
        nxt = _schedule_followup(db, problem)
        out["next_followup"] = {"id": nxt.id, "due_on": nxt.due_on.isoformat()}
    db.commit()
    return out


# --------------------------------------------------------------------------
# Expert
# --------------------------------------------------------------------------


def case_bundle(db: Session, kb: KB, case: Case, lang: str = "en") -> dict:
    problem = db.get(Problem, case.problem_id)
    farm = problem.farm
    diags = problem.diagnoses
    last = diags[-1] if diags else None
    obs = problem.observations
    traps = db.scalars(
        select(TrapReading).where(TrapReading.farm_id == farm.id).order_by(TrapReading.recorded_on.desc())
    ).all()[:10]
    alerts = db.scalars(
        select(Alert).where(Alert.farm_id == farm.id).order_by(Alert.issued_on.desc())
    ).all()[:10]
    fus = db.scalars(select(FollowUp).where(FollowUp.problem_id == problem.id)).all()
    history = db.scalars(
        select(Confirmation).join(Problem, Confirmation.problem_id == Problem.id)
        .where(Problem.farm_id == farm.id, Problem.id != problem.id)
    ).all()
    return {
        "case": case_brief(db, case) | {"created_at": case.created_at.isoformat() if case.created_at else None},
        "farm": farm_view(kb, farm, lang),
        "problem": {"id": problem.id, "severity": problem.severity, "status": problem.status},
        "photos": [_image_url(d.image_path) for d in diags if d.image_path],
        "heatmaps": [d.heatmap for d in diags if d.image_path],  # aligned with photos; null = none
        "model": {
            "version": last.model_version if last else None,
            "is_stub": last.is_stub if last else None,
            "gate_reason": last.gate_reason if last else case.reason,
            "hypotheses": [
                _pred_view(kb, gate.Prediction(p["target"], p["confidence"]), lang) for p in (last.topk if last else [])
            ],
        },
        "doubt_doctor": [
            {"question": o.question, "answer": o.answer, "cue_id": o.cue_id} for o in obs if o.kind == "doubt_doctor"
        ],
        "followups": [{"due_on": f.due_on.isoformat(), "response": f.response} for f in fus],
        "trap_readings": [
            {"target": t.target, "recorded_on": t.recorded_on.isoformat(), "count": t.count,
             "traps": t.traps, "nights": t.nights, "per_trap_night": round(t.count / (t.traps * t.nights), 1)}
            for t in traps
        ],
        "recent_alerts": [alert_view(kb, a, lang) for a in alerts],
        "farm_history": [{"final_label": h.final_label, "verdict": h.verdict,
                          "on": h.created_at.date().isoformat() if h.created_at else None} for h in history],
        "candidate_labels": [
            kb.target_view(t, lang) for t, v in kb.targets.items() if v["crop"] == farm.crop
        ],
        "icar_referral": icar_referral(kb, [p["target"] for p in (last.topk if last else [])], farm.crop, lang),
        "satellite": case_satellite(db, kb, farm),
    }


def case_satellite(db: Session, kb: KB, farm: Farm) -> dict | None:
    """This field's greenness trend, for the expert reading the case.

    Evidence the photo cannot give: whether the whole field is losing vigour, or
    only the leaf in the picture. Best-effort — no key, no clear scene or a
    provider outage simply means the card is not shown."""
    from app.engine import satellite  # noqa: PLC0415  optional, and it reaches the network

    if not satellite.configured() or not farm.agro_polygon_id:
        return None
    try:
        stage, _ = kb.stage_for(farm.crop, farm.sowing_date, date.today())
        s = satellite.summarize(satellite.ndvi_series(farm.agro_polygon_id), farm.crop, stage)
    except satellite.SatelliteUnavailable:
        return None
    if not s.get("available"):
        return None
    return {
        "latest": s["latest"], "previous": s.get("previous"), "change": s.get("change"),
        "band": s.get("band"), "drop": s.get("drop"), "age_days": s.get("age_days"),
        "quiet_stage": s.get("quiet_stage"),
        "series": [{"on": p["on"], "mean": p["mean"], "source": p.get("source")} for p in s.get("series", [])],
    }


def icar_referral(kb: KB, targets: list[str], crop: str, lang: str) -> list[dict]:
    """ICAR technologies and institutes for the suspected problems first, then
    the crop-level tools and references — what an expert refers the farmer or
    the extension office to."""
    out, seen = [], set()
    for t in targets:
        if kb.targets.get(t, {}).get("crop") != crop:
            continue  # a maize guess on a rice farm is not a referral for this farm
        for x in kb.technologies_for(target=t):
            if x["id"] not in seen:
                seen.add(x["id"])
                out.append(kb.tech_view(x, lang) | {"for_target": t})
    for x in kb.technologies_for(crop=crop):
        if x["id"] not in seen and not x["targets"]:
            seen.add(x["id"])
            out.append(kb.tech_view(x, lang) | {"for_target": None})
    return out


HEALTHY_VERDICT = "healthy"
"""The expert looked and found nothing wrong. Not a disease, so it carries no
advisory, warns no neighbour and teaches the label prior nothing."""

OTHER_VERDICT = "other"
"""Something real that this app cannot name — a disease outside the knowledge
base, a nutrient or water problem, damage. The officer must say what it is in
their notes; the farmer is told a person looked and what they wrote. Nothing is
invented: with no authored advisory for it, the app offers none."""

SPECIAL_VERDICTS = (HEALTHY_VERDICT, OTHER_VERDICT)


def resolve_case(
    db: Session, kb: KB, case: Case, *, verdict: str, final_label: str, expert_name: str,
    notes: str | None, referred_to_lab: bool, today: date | None = None,
) -> dict:
    if case.status != "open":
        raise ValueError("case already resolved")
    problem = db.get(Problem, case.problem_id)
    farm = problem.farm
    special = final_label in SPECIAL_VERDICTS
    if not special and (final_label not in kb.targets or kb.targets[final_label]["crop"] != farm.crop):
        raise ValueError(f"{final_label} is not a {farm.crop} target")
    if final_label == OTHER_VERDICT and not (notes or "").strip():
        raise ValueError("say what it is: a note naming the problem is required")
    last = problem.diagnoses[-1] if problem.diagnoses else None
    model_label = last.topk[0]["target"] if last and last.topk else None
    if verdict == "confirmed" and model_label and model_label != final_label:
        verdict = "corrected"

    conf = Confirmation(
        case_id=case.id, problem_id=problem.id, verdict=verdict, model_label=model_label,
        final_label=final_label, expert_name=expert_name, notes=notes, referred_to_lab=referred_to_lab,
    )
    db.add(conf)
    case.status, case.resolved_at = "resolved", datetime.now(UTC)

    # Learning from field confirmations: counts only.
    def bump(target: str, field: str):
        row = db.get(LabelPrior, (farm.district, farm.crop, target))
        if row is None:
            row = LabelPrior(district=farm.district, crop=farm.crop, target=target, confirmed=0, corrected=0)
            db.add(row)
        setattr(row, field, getattr(row, field) + 1)

    # A sentinel is not one of the model's labels, so it teaches the prior
    # nothing about what to predict — but being wrong still counts against the
    # label the model did put forward.
    if not special:
        bump(final_label, "confirmed")
    if model_label and model_label != final_label and model_label in kb.targets:
        bump(model_label, "corrected")

    if special:
        problem.target = None  # neither sentinel is a label the rest of the app can act on
        problem.status = "resolved"
        problem.resolved_at = datetime.now(UTC)
        advice, spread = {"followup": None}, 0
    else:
        advice = _advise(db, kb, problem, final_label, "expert", farm.lang, farm)
        spread = propagate(db, kb, farm, final_label, case.id, today)
    db.commit()
    return {
        "confirmation_id": conf.id, "verdict": verdict, "final_label": final_label,
        "model_label": model_label, "spread_alerts": spread, "followup": advice["followup"],
    }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def propagate(db: Session, kb: KB, origin: Farm, target: str, case_id: int, today: date | None = None) -> int:
    """Only expert-confirmed cases reach here. An unconfirmed model output must
    never trigger a village-wide alarm."""
    today = today or date.today()
    rule = kb.rules[target]
    t = kb.targets[target]
    issued = 0
    for farm in db.scalars(select(Farm).where(Farm.crop == origin.crop, Farm.id != origin.id)).all():
        km = haversine_km(origin.lat, origin.lon, farm.lat, farm.lon)
        if km > SPREAD_RADIUS_KM:
            continue
        exists = db.scalar(select(Alert.id).where(
            Alert.farm_id == farm.id, Alert.target == target, Alert.trigger == "spread", Alert.issued_on == today
        ))
        if exists:
            continue
        db.add(Alert(
            farm_id=farm.id, target=target, trigger="spread", level="high",
            reason=risk.spread_reason(t["names"], kb.crops[origin.crop]["names"], km),
            tasks=rule["tasks"], issued_on=today, source_case_id=case_id,
        ))
        issued += 1
    db.flush()
    return issued


# --------------------------------------------------------------------------
# Risk
# --------------------------------------------------------------------------

REISSUE_AFTER_DAYS = {"weather": 3, "weather+phenology": 3, "phenology": 7, "trap": 1}


def weather_for(db: Session, farm: Farm):
    try:
        window = fetch_window(farm.lat, farm.lon)
    except WeatherUnavailable:
        return None
    # Satellite-observed rain for past days (INSAT-3DS via MOSDAC), then the
    # farmer's own sensor or gauge on top: the closer to the field, the later.
    from app import mosdac
    observed = {d: mm for d, mm in mosdac.trusted(mosdac.observed_days(db, farm.lat, farm.lon)).items()
                if d < date.today()}
    window = merge_rain(window, observed)
    since = date.today() - timedelta(days=14)
    readings = db.scalars(
        select(SensorReading).where(SensorReading.farm_id == farm.id, SensorReading.on >= since)
    ).all()
    if readings:
        window = merge_sensor(window, [
            {"on": r.on, "rh_max": r.rh_max, "t_min": r.t_min, "t_max": r.t_max, "rain_mm": r.rain_mm}
            for r in readings
        ])
    return window


def satellite_drop(summary: dict | None) -> dict | None:
    """The greenness drop to quote in a reason, or None. Shaped for risk.REASONS."""
    if not summary or not summary.get("available") or not summary.get("drop"):
        return None
    if summary.get("age_days") is not None and summary["age_days"] > SATELLITE_MAX_AGE_DAYS:
        return None  # the last clear scene is too old to say anything about today
    last, prev = summary["latest"], summary["previous"]
    return {"before": prev["mean"], "after": last["mean"], "d1": prev["on"], "d2": last["on"]}


def risk_scores(db: Session, kb: KB, farm: Farm, today: date, window,
                satellite: dict | None = None) -> list[risk.Score]:
    """Every rule that fires for this farm today, highest level first. Read-only.

    `satellite` is this farm's greenness-drop summary when the caller already
    has one (the watcher does); it only ever raises a level that already fired."""
    stage, das = kb.stage_for(farm.crop, farm.sowing_date, today)
    history = set(db.scalars(
        select(Problem.target).where(Problem.farm_id == farm.id, Problem.target.is_not(None))
    ).all())

    scores: list[risk.Score] = []
    for target, rule in kb.rules.items():
        if kb.targets[target]["crop"] != farm.crop:
            continue
        s = risk.score_rule(
            target, rule,
            target_name=kb.targets[target]["names"],
            stage=stage,
            stage_name=next(x["names"] for x in kb.crops[farm.crop]["stages"] if x["key"] == stage),
            das=das, window=window, has_history=target in history, today=today,
            satellite=satellite,
        )
        if s.fired:
            scores.append(s)
        if rule.get("trap"):
            readings = db.scalars(select(TrapReading).where(
                TrapReading.farm_id == farm.id, TrapReading.target == target,
                TrapReading.recorded_on >= today - timedelta(days=14),
            )).all()
            ts = risk.score_traps(target, rule, [
                {"recorded_on": r.recorded_on, "count": r.count, "traps": r.traps, "nights": r.nights}
                for r in readings
            ], today)
            if ts.fired:
                scores.append(ts)

    order = {"high": 0, "medium": 1, "low": 2}
    scores.sort(key=lambda s: order[s.level])
    return scores


def run_risk(db: Session, kb: KB, farm: Farm, today: date | None = None, window=...,
             satellite: dict | None = None) -> dict:
    today = today or date.today()
    if window is ...:
        window = weather_for(db, farm)
    scores = risk_scores(db, kb, farm, today, window, satellite=satellite)
    issued = []
    # The cap is per farm per DAY, so alerts from an earlier run today count.
    calendar_count = db.scalar(select(func.count(Alert.id)).where(
        Alert.farm_id == farm.id, Alert.issued_on == today, Alert.trigger.not_in(("trap", "spread")),
    )) or 0
    for s in scores:
        is_calendar = s.trigger != "trap"
        if is_calendar and calendar_count >= MAX_RISK_ALERTS_PER_FARM_PER_DAY:
            continue
        window_days = REISSUE_AFTER_DAYS.get(s.trigger, 3)
        recent = db.scalar(select(Alert.id).where(
            Alert.farm_id == farm.id, Alert.target == s.target, Alert.trigger == s.trigger,
            Alert.issued_on > today - timedelta(days=window_days),
        ))
        if recent:
            continue
        a = Alert(
            farm_id=farm.id, target=s.target, trigger=s.trigger, level=s.level, reason=s.reason,
            tasks=kb.rules[s.target]["tasks"], issued_on=today,
        )
        db.add(a)
        db.flush()
        issued.append(a.id)
        if is_calendar:
            calendar_count += 1
    db.commit()
    return {
        "farm_id": farm.id,
        "issued": issued,
        "evaluated": len([t for t in kb.rules if kb.targets[t]["crop"] == farm.crop]),
        "fired": [{"target": s.target, "level": s.level, "trigger": s.trigger, "detail": s.detail} for s in scores],
        "weather_source": window.source if window else "unavailable",
        "satellite_bump": bool(satellite),
    }


RAIN_CONTEXT = {
    "en": "{month} so far: {obs} mm of rain vs {exp} mm normal to date for {sub} ({dep:+.0f}%).",
    "hi": "{month} में अब तक: {obs} मिमी बारिश, जबकि {sub} में इस तारीख तक सामान्य {exp} मिमी ({dep:+.0f}%)।",
    "mr": "{month} मध्ये आतापर्यंत: {obs} मिमी पाऊस, तर {sub} मध्ये या तारखेपर्यंत सामान्य {exp} मिमी ({dep:+.0f}%).",
}
MONTH_KEYS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


@lru_cache
def rainfall_normals() -> dict:
    return json.loads((KB_DIR / "imd_rainfall_normals.json").read_text(encoding="utf-8"))


@lru_cache
def kcc_signals() -> dict | None:
    """Kisan Call Centre call patterns (built by data/kcc_signals.py); None if absent."""
    path = KB_DIR / "kcc_signals.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def kcc_seasonal(kb: KB, farm: Farm, month: int, lang: str) -> list[dict]:
    """Pest groups on this farm's crop whose KCC calls peak this month, the
    farm's own district first."""
    data = kcc_signals()
    if not data:
        return []
    out = []
    for g in data["groups"]:
        if g["crop"] != farm.crop or month not in g["peak_months"]:
            continue
        local = (g.get("district_months", {}).get(farm.district) or {}).get(str(month), 0)
        name = tr(kb.targets[g["targets"][0]]["names"], lang) if g["targets"] and g["targets"][0] in kb.targets \
            else g["label"]
        out.append({"group": g["id"], "name": name, "targets": g["targets"], "district_calls_this_month": local,
                    "state_share_this_month": g["month_share"][str(month)], "calls": g["calls"]})
    return sorted(out, key=lambda x: (-x["district_calls_this_month"], -x["calls"]))[:4]


def rain_vs_normal(district: str, lat: float, lon: float, today: date | None = None) -> dict | None:
    """This month's rain so far against the IMD 1901-2015 normal for the
    district's subdivision, prorated to today's date."""
    today = today or date.today()
    normals = rainfall_normals()
    sub = normals["district_to_subdivision"].get(district)
    if sub is None:
        return None
    month = MONTH_KEYS[today.month - 1]
    normal_month = normals["subdivisions"][sub]["mean"].get(month)
    observed = fetch_month_rain(lat, lon)
    if observed is None or not normal_month:
        return {"subdivision": sub, "month": month, "normal_month_mm": normal_month, "observed_mm": None}
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    expected = normal_month * observed["days"] / days_in_month
    dep = (observed["rain_mm"] - expected) / expected * 100 if expected else 0.0
    return {
        "subdivision": sub, "month": month, "normal_month_mm": normal_month,
        "expected_to_date_mm": round(expected, 1), "observed_mm": observed["rain_mm"],
        "departure_pct": round(dep), "days": observed["days"], "source": observed["source"],
        "normal_source": "IMD 1901-2015 subdivision mean",
    }


def rain_context(kb: KB, farm: Farm, lang: str) -> dict | None:
    rc = rain_vs_normal(farm.district, farm.lat, farm.lon)
    if rc is None or rc.get("observed_mm") is None:
        return rc
    month_name = i18n_month(date.today().month, lang)
    sub_name = rc["subdivision"].title().replace("&", "and")
    rc["text"] = tr(RAIN_CONTEXT, lang).format(
        month=month_name, obs=rc["observed_mm"], exp=rc["expected_to_date_mm"], sub=sub_name,
        dep=rc["departure_pct"],
    )
    return rc


def weather_summary(window) -> dict | None:
    if window is None:
        return {"source": "unavailable", "days": []}
    today = date.today()
    return {
        "source": window.source,
        "fetched_at": window.fetched_at.isoformat(),
        "days": [
            {"on": d.on.isoformat(), "rh_max": d.rh_max, "t_min": d.t_min, "t_max": d.t_max,
             "rain_mm": d.rain_mm, "forecast": d.on > today, "from_sensor": d.from_sensor}
            for d in window.days
        ],
    }


def record_alert_outcome(db: Session, kb: KB, alert: Alert, outcome: str, lang: str) -> dict:
    alert.outcome, alert.outcome_at = outcome, datetime.now(UTC)
    out: dict = {"alert_id": alert.id, "outcome": outcome}
    t = kb.targets[alert.target]
    if outcome == "found" and not (t["tier"] == "diagnosable" and kb.crops[t["crop"]]["photo_diagnosis"]):
        # Inspection-tier finding: a human confirms it; no photo gate to pass.
        problem = Problem(farm_id=alert.farm_id, target=None, severity="medium")
        db.add(problem)
        db.flush()
        db.add(Observation(problem_id=problem.id, kind="field_note", cue_id=None,
                           question=f"Alert {alert.target}: inspection tasks", answer="yes"))
        case = escalate(db, problem, "INSPECTION_FOUND")
        out |= {"case": case_brief(db, case), "problem_id": problem.id, "message": msg("INSPECTION_FOUND", lang)}
    db.commit()
    return out
