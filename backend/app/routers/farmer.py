"""Endpoints the farmer app calls. All text comes back in `lang`."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, config, nim, services
from app.db import get_db
from app.limits import limit
from app.engine import labelcheck, vision
from app.kb import KB, get_kb, tr
from app.models import Alert, Farm, FollowUp, Problem, SensorReading, TrapReading

# Every /farms/{farm_id}, /problems/{id}, /alerts/{id} and /followups/{id} URL is
# checked against the signed-in farmer (app.auth.guard); experts may open any farm.
router = APIRouter(prefix="/api", tags=["farmer"], dependencies=[Depends(auth.require())])
Lang = Literal["en", "hi", "mr", "bn", "ta", "te", "kn", "ml", "gu", "pa"]  # Odia off for now: app/i18n.py
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _farm(db: Session, farm_id: int) -> Farm:
    farm = db.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")
    return farm


def _problem(db: Session, problem_id: int) -> Problem:
    p = db.get(Problem, problem_id)
    if p is None:
        raise HTTPException(404, "problem not found")
    return p


@router.get("/kb/crops")
def crops(lang: Lang = "en", kb: KB = Depends(get_kb)):
    return [
        {"id": cid, "name": tr(c["names"], lang), "photo_diagnosis": c["photo_diagnosis"],
         "stages": [{"key": s["key"], "name": tr(s["names"], lang), "das": s["das"]} for s in c["stages"]]}
        for cid, c in kb.crops.items()
    ]


@router.get("/kb/targets")
def targets(lang: Lang = "en", crop: str | None = None, kb: KB = Depends(get_kb)):
    return [kb.target_view(t, lang) for t, v in kb.targets.items() if crop is None or v["crop"] == crop]


@router.get("/samples")
def samples(request: Request, crop: str | None = None, per_class: int = 1,
            db: Session = Depends(get_db)):
    """Held-out TEST images (never seen in training) for showing the app without
    a sick plant at hand. Empty when the dataset or split is not on this machine.

    Demo accounts only. A farmer who signed up for their own field is looking at
    their own crop, and a strip of somebody else's photos in the middle of that
    is not something they should have to tell apart from their own."""
    user = auth.current_user(request, db)
    if not (user and user.is_demo):
        return []
    split = vision.ARTIFACTS / "split.json"
    if not split.exists():
        return []
    import json as _json  # noqa: PLC0415

    sp = _json.loads(split.read_text())
    test = sp.get("test", []) + sp.get("extra_test", [])
    # What the live pipeline does with each photo (ml/sample_outcomes.py), so a
    # presenter can pick the one that asks a question or goes to an expert.
    oc_file = vision.ARTIFACTS / "sample_outcomes.json"
    outcomes = _json.loads(oc_file.read_text())["samples"] if oc_file.exists() else {}
    seen: dict[str, int] = {}
    featured: list[dict] = []
    out = []
    n_escalate = 0
    for path in test:
        cls = path.split("/")[-2]
        if crop and not cls.startswith(crop + "_"):
            continue
        key = "/".join(path.split("/")[-2:])
        # Each processed set has its own mount (app.main); ICAR photos sit one
        # directory shallower, the others under their source folder.
        mount = next((m for d, m in (("/extra_640/", "/samples-extra/"), ("/more_640/", "/samples-more/"))
                      if d in path), None)
        url = mount + "/".join(path.split("/")[-3:]) if mount else "/samples/" + key
        item = {"url": url, "true_class": cls, "source": path.split("/")[-3] if mount else "icar",
                "expected": outcomes.get(key, {}).get("outcome")}
        if item["expected"] == "clarify" or (item["expected"] == "escalate" and n_escalate < 2):
            n_escalate += item["expected"] == "escalate"
            featured.append(item)
        elif seen.get(cls, 0) < per_class:
            seen[cls] = seen.get(cls, 0) + 1
            out.append(item)
    featured.sort(key=lambda s: s["expected"] != "clarify")
    return featured + out


@router.get("/kb/technologies")
def technologies(lang: Lang = "en", crop: str | None = None, target: str | None = None,
                 audience: Literal["farmer", "official"] | None = None, kb: KB = Depends(get_kb)):
    """ICAR technology repository entries linked to our crops and targets."""
    return [kb.tech_view(t, lang) for t in kb.technologies_for(target=target, crop=crop, audience=audience)]


@router.get("/kb/pesticides")
def pesticides(kb: KB = Depends(get_kb)):
    return [{"id": pid, "name": p["name"], "class": p["class"]} for pid, p in kb.pesticides.items()]


class FarmIn(BaseModel):
    farmer_name: str = Field(min_length=1, max_length=120)
    phone: str | None = None
    lang: Lang = "mr"
    crop: str
    variety: str | None = None
    sowing_date: date
    district: str
    village: str | None = None
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    area_acres: float = Field(gt=0, le=1000)
    soil: str | None = None
    soil_ph: float | None = Field(default=None, ge=3, le=11)  # from the Soil Health Card, if the farmer has one
    soil_ph_on: date | None = None
    irrigation: Literal["rainfed", "canal", "borewell", "open_well", "farm_pond", "drip", "sprinkler"] | None = None


@router.get("/farms")
def list_farms(request: Request, lang: Lang = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    """The signed-in farmer's farms (a demo farmer: the demo farms; an expert: all)."""
    ids = auth.farm_ids_for(db, auth.signed_in(request, db))
    q = select(Farm).order_by(Farm.id)
    if ids is not None:
        q = q.where(Farm.id.in_(ids))
    return [services.farm_view(kb, f, lang) for f in db.scalars(q).all()]


@router.post("/farms", status_code=201)
def create_farm(body: FarmIn, request: Request, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    """Another field for the signed-in farmer (the first comes with sign-up)."""
    user = auth.signed_in(request, db)
    if user is not None and user.role != "farmer":
        raise HTTPException(403, "only farmers add farms")
    if body.crop not in kb.crops:
        raise HTTPException(422, f"unsupported crop {body.crop}")
    farm = Farm(**body.model_dump(), user_id=user.id if user else None)
    if user is not None:  # the account's contact details reach this field's alerts too
        farm.phone = farm.phone or user.phone
        farm.email = user.email
    db.add(farm)
    db.commit()
    return services.farm_view(kb, farm, body.lang)


class FarmPrefs(BaseModel):
    lang: Lang | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


@router.patch("/farms/{farm_id}")
def update_farm(farm_id: int, body: FarmPrefs, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    """The farmer's preferred language (the app, the voice, notifications and
    emails all follow it), and the field's own spot once they allow location —
    everything from the weather to the outbreak radius is read there."""
    farm = _farm(db, farm_id)
    if body.lang:
        farm.lang = body.lang
    if body.lat is not None and body.lon is not None:
        farm.lat, farm.lon, farm.location_source = body.lat, body.lon, "gps"
        farm.agro_polygon_id = None  # the satellite field polygon is redrawn around the new spot
    db.commit()
    return services.farm_view(kb, farm, body.lang or farm.lang)


@router.get("/farms/{farm_id}")
def get_farm(farm_id: int, lang: Lang = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    return services.farm_view(kb, _farm(db, farm_id), lang)


@router.get("/farms/{farm_id}/home")
def home(farm_id: int, lang: Lang = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = _farm(db, farm_id)
    window = services.weather_for(db, farm)
    alerts = db.scalars(
        select(Alert).where(Alert.farm_id == farm.id).order_by(Alert.issued_on.desc(), Alert.id.desc())
    ).all()
    problems = db.scalars(
        select(Problem).where(Problem.farm_id == farm.id).order_by(Problem.id.desc())
    ).all()[:8]
    due = db.scalars(
        select(FollowUp).join(Problem, FollowUp.problem_id == Problem.id)
        .where(Problem.farm_id == farm.id, FollowUp.response.is_(None), FollowUp.due_on <= date.today())
    ).all()
    return {
        "farm": services.farm_view(kb, farm, lang),
        "weather": services.weather_summary(window),
        "rain_context": services.rain_context(kb, farm, lang),
        "alerts": [services.alert_view(kb, a, lang) for a in alerts if a.outcome in (None, "snoozed")],
        "problems": services.problem_views(db, kb, list(problems), lang),
        "followups_due": [{"id": f.id, "problem_id": f.problem_id, "due_on": f.due_on.isoformat()} for f in due],
        "model": vision.model_status(),
    }


@router.post("/farms/{farm_id}/diagnose")
async def diagnose(
    farm_id: int,
    image: UploadFile = File(...),
    lang: Lang = Form("en"),
    demo_scenario: str | None = Form(None),
    db: Session = Depends(get_db),
    kb: KB = Depends(get_kb),
):
    farm = _farm(db, farm_id)
    limit(f"diagnose:{farm_id}", 30, 60)
    data = await image.read()
    if not data:
        raise HTTPException(422, "empty image")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "image too large (max 12 MB)")
    try:
        return services.diagnose(db, kb, farm, data, lang, demo_scenario)
    except vision.UnreadableImage as exc:
        raise HTTPException(422, "could not read the image — try another photo") from exc


class ClarifyIn(BaseModel):
    cue_id: str
    answer: Literal["yes", "no", "unknown"]
    lang: Lang = "en"


@router.post("/problems/{problem_id}/clarify")
def clarify(problem_id: int, body: ClarifyIn, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    problem = _problem(db, problem_id)
    try:
        return services.answer_clarify(db, kb, problem, body.cue_id, body.answer, body.lang)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/problems/{problem_id}/escalate")
def escalate(problem_id: int, lang: Lang = "en", db: Session = Depends(get_db)):
    problem = _problem(db, problem_id)
    case = services.escalate(db, problem, "FARMER_REQUEST")
    db.commit()
    return {"case": services.case_brief(db, case), "message": services.msg("FARMER_REQUEST", lang)}


@router.get("/problems/{problem_id}")
def get_problem(problem_id: int, lang: Lang = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    return services.problem_view(db, kb, _problem(db, problem_id), lang)


class FollowUpIn(BaseModel):
    response: Literal["improved", "no_change", "got_worse"]
    lang: Lang = "en"


@router.get("/problems/{problem_id}/result")
def problem_result(problem_id: int, lang: Lang = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    """The photo result screen again in `lang` — for a language switch on it."""
    try:
        return services.result_view(db, kb, _problem(db, problem_id), lang)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/followups/{followup_id}")
def followup(followup_id: int, body: FollowUpIn, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    fu = db.get(FollowUp, followup_id)
    if fu is None:
        raise HTTPException(404, "follow-up not found")
    if fu.response is not None:
        raise HTTPException(409, "follow-up already answered")
    return services.respond_followup(db, kb, fu, body.response, body.lang)


@router.get("/farms/{farm_id}/alerts")
def alerts(farm_id: int, lang: Lang = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = _farm(db, farm_id)
    rows = db.scalars(
        select(Alert).where(Alert.farm_id == farm.id).order_by(Alert.issued_on.desc(), Alert.id.desc())
    ).all()
    return [services.alert_view(kb, a, lang) for a in rows]


class AlertOutcomeIn(BaseModel):
    outcome: Literal["nothing_found", "found", "snoozed"]
    lang: Lang = "en"


@router.post("/alerts/{alert_id}/outcome")
def alert_outcome(alert_id: int, body: AlertOutcomeIn, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    return services.record_alert_outcome(db, kb, alert, body.outcome, body.lang)


@router.post("/farms/{farm_id}/risk/run")
def run_risk(farm_id: int, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    return services.run_risk(db, kb, _farm(db, farm_id))


class TrapIn(BaseModel):
    target: str
    trap_type: Literal["pheromone", "light", "yellow_sticky"] = "pheromone"
    count: int = Field(ge=0, le=100000)
    traps: int = Field(default=1, ge=1, le=100)
    nights: int = Field(default=1, ge=1, le=14)
    recorded_on: date | None = None


@router.post("/farms/{farm_id}/traps", status_code=201)
def add_trap(farm_id: int, body: TrapIn, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = _farm(db, farm_id)
    if body.target not in kb.targets or kb.targets[body.target]["crop"] != farm.crop:
        raise HTTPException(422, f"{body.target} is not a {farm.crop} pest")
    db.add(TrapReading(farm_id=farm.id, **body.model_dump(exclude={"recorded_on"}),
                       recorded_on=body.recorded_on or date.today()))
    db.commit()
    return services.run_risk(db, kb, farm)


@router.get("/farms/{farm_id}/traps")
def list_traps(farm_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(TrapReading).where(TrapReading.farm_id == farm_id).order_by(TrapReading.recorded_on.desc())
    ).all()
    return [{"id": r.id, "target": r.target, "trap_type": r.trap_type, "count": r.count, "traps": r.traps,
             "nights": r.nights, "recorded_on": r.recorded_on.isoformat(),
             "per_trap_night": round(r.count / (r.traps * r.nights), 1)} for r in rows]


class SensorIn(BaseModel):
    on: date
    rh_max: float | None = Field(default=None, ge=0, le=100)
    t_min: float | None = Field(default=None, ge=-10, le=55)
    t_max: float | None = Field(default=None, ge=-10, le=55)
    rain_mm: float | None = Field(default=None, ge=0, le=1000)
    leaf_wetness_h: float | None = Field(default=None, ge=0, le=24)
    soil_ph: float | None = Field(default=None, ge=3, le=11)
    soil_moisture_pct: float | None = Field(default=None, ge=0, le=100)


@router.post("/farms/{farm_id}/sensor", status_code=201)
def add_sensor(farm_id: int, readings: list[SensorIn], db: Session = Depends(get_db)):
    farm = _farm(db, farm_id)
    for r in readings:
        row = db.scalar(select(SensorReading).where(SensorReading.farm_id == farm.id, SensorReading.on == r.on))
        if row is None:
            row = SensorReading(farm_id=farm.id, on=r.on)
            db.add(row)
        for k, v in r.model_dump(exclude={"on"}, exclude_unset=True).items():
            setattr(row, k, v)  # only what the device sent; a pH-only reading keeps the day's weather
    db.commit()
    return {"stored": len(readings)}


class LabelCheckIn(BaseModel):
    farm_id: int
    product: str = Field(min_length=1, max_length=120)
    problem_id: int | None = None
    lang: Lang = "en"


@router.post("/labelcheck")
def label_check(body: LabelCheckIn, request: Request, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farm = _farm(db, body.farm_id)
    auth.check_farm(auth.signed_in(request, db), farm)
    target = None
    if body.problem_id is not None:
        target = _problem(db, body.problem_id).target
    else:
        latest = db.scalar(select(Problem).where(
            Problem.farm_id == farm.id, Problem.status == "open", Problem.target.is_not(None)
        ).order_by(Problem.id.desc()))
        target = latest.target if latest else None
    if target and target.endswith("_healthy"):
        target = None
    out = labelcheck.check(kb, body.product, farm.crop, target, body.lang) | {"target": target}
    if out["tone"] == "unknown":
        # We hold no record of what was typed, so the verified answer stops at
        # "ask an expert". A model can still say what the thing IS — that water
        # is not a pesticide, that a fertiliser will not cure a fungus — which is
        # the difference between a dead end and an answer. It explains only:
        # labelcheck.safe_suggestion drops anything carrying a dose or naming a
        # chemical, and the verified refusal above is never replaced.
        problem = tr(kb.targets[target]["names"], "en") if target else "not diagnosed yet"
        out["suggestion"] = labelcheck.safe_suggestion(kb, nim.suggest(
            body.product, tr(kb.crops[farm.crop]["names"], "en"), problem, body.lang,
            key=config.NVIDIA_SUGGEST_KEY))
    return out
