"""Read-only surveillance for agriculture officials: where problems are, how
the system is performing in the field, and what the weather is doing to risk.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app import auth, services
from app.db import get_db
from app.engine import vision
from app.kb import KB, get_kb, tr
from app.models import Advisory, Alert, Case, Confirmation, Diagnosis, Farm, Problem

router = APIRouter(prefix="/api/officials", tags=["officials"], dependencies=[Depends(auth.require("expert"))])

# One representative point per Maharashtra IMD subdivision for the rainfall panel.
SUBDIVISION_POINTS = {
    "KONKAN & GOA": ("Ratnagiri", 16.99, 73.31),
    "MADHYA MAHARASHTRA": ("Pune", 18.52, 73.86),
    "MARATHWADA": ("Chhatrapati Sambhajinagar", 19.88, 75.34),
    "VIDARBHA": ("Nagpur", 21.15, 79.09),
}


@router.get("/summary")
def summary(lang: str = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    farms = db.scalars(select(Farm)).all()
    diags = db.scalars(select(Diagnosis)).all()
    cases = db.scalars(select(Case)).all()
    confs = db.scalars(select(Confirmation)).all()
    alerts = db.scalars(select(Alert)).all()
    problems = db.scalars(select(Problem)).all()
    advised = {a.problem_id for a in db.scalars(select(Advisory)).all()}
    confirmed_problems = {c.problem_id for c in confs}

    gate_outcomes = Counter(d.gate_outcome for d in diags)
    reasons = Counter(d.gate_reason for d in diags if d.gate_outcome == "escalate")
    verdicts = Counter(c.verdict for c in confs)
    n_conf = verdicts["confirmed"] + verdicts["corrected"]

    acc: dict[str, Counter] = defaultdict(Counter)
    for c in confs:
        if c.model_label:
            acc[c.model_label][c.verdict] += 1

    farm_by_id = {f.id: f for f in farms}
    by_district: dict[str, Counter] = defaultdict(Counter)
    for f in farms:
        by_district[f.district]["farms"] += 1
    targets: dict[str, Counter] = defaultdict(Counter)
    for p in problems:
        if not p.target or p.target.endswith("_healthy"):
            continue
        d = farm_by_id[p.farm_id].district
        if p.id in confirmed_problems:
            by_district[d]["confirmed"] += 1
            targets[p.target]["confirmed"] += 1
        elif p.id in advised:
            by_district[d]["suspected"] += 1
            targets[p.target]["suspected"] += 1
    for c in cases:
        if c.status == "open":
            p = db.get(Problem, c.problem_id)
            by_district[farm_by_id[p.farm_id].district]["open_cases"] += 1
    for a in alerts:
        if a.outcome is None and a.level == "high":
            by_district[farm_by_id[a.farm_id].district]["active_high_alerts"] += 1

    answered = [a for a in alerts if a.outcome in ("nothing_found", "found")]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "includes_demo_data": any(f.is_demo for f in farms),
        "model": vision.model_status(),
        "totals": {
            "farms": len(farms),
            "diagnoses": len(diags),
            "open_cases": sum(c.status == "open" for c in cases),
            "resolved_cases": sum(c.status == "resolved" for c in cases),
            "confirmed": verdicts["confirmed"],
            "corrected": verdicts["corrected"],
            "field_accuracy": round(verdicts["confirmed"] / n_conf, 3) if n_conf else None,
            "alerts_issued": len(alerts),
            "alerts_answered": len(answered),
            "alerts_found": sum(a.outcome == "found" for a in answered),
            "referred_to_lab": sum(c.referred_to_lab for c in confs),
        },
        "gate_outcomes": dict(gate_outcomes),
        "escalation_reasons": dict(reasons),
        "alerts_by_trigger": dict(Counter(a.trigger for a in alerts)),
        "by_district": sorted(
            [{"district": d, **{k: v.get(k, 0) for k in
              ("farms", "confirmed", "suspected", "open_cases", "active_high_alerts")}}
             for d, v in by_district.items()],
            key=lambda r: (-r["confirmed"], -r["suspected"], r["district"]),
        ),
        "top_targets": sorted(
            [{"target": t, "name": tr(kb.targets[t]["names"], lang), "crop": kb.targets[t]["crop"],
              "confirmed": v["confirmed"], "suspected": v["suspected"]}
             for t, v in targets.items() if t in kb.targets],
            key=lambda r: (-r["confirmed"], -r["suspected"]),
        ),
        "accuracy_by_label": sorted(
            [{"model_label": t, "name": tr(kb.targets[t]["names"], lang) if t in kb.targets else t,
              "confirmed": v["confirmed"], "corrected": v["corrected"]} for t, v in acc.items()],
            key=lambda r: -(r["confirmed"] + r["corrected"]),
        ),
    }


@router.get("/hotspots")
def hotspots(days: int = 45, lang: str = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    confs = {c.problem_id: c for c in db.scalars(select(Confirmation)).all()}
    advised = {a.problem_id for a in db.scalars(select(Advisory)).all()}
    open_case = {c.problem_id for c in db.scalars(select(Case).where(Case.status == "open")).all()}
    points = []
    for p in db.scalars(select(Problem).options(joinedload(Problem.farm)).where(Problem.opened_at >= since)).all():
        f = p.farm
        if p.id in confs:
            status, target = "confirmed", confs[p.id].final_label
        elif p.id in open_case:
            status, target = "awaiting_expert", p.target
        elif p.id in advised:
            status, target = "suspected", p.target
        else:
            continue
        if target and target.endswith("_healthy"):
            continue
        points.append({
            "problem_id": p.id, "lat": f.lat, "lon": f.lon, "district": f.district, "crop": f.crop,
            "target": target, "name": tr(kb.targets[target]["names"], lang) if target in kb.targets else None,
            "status": status, "on": p.opened_at.date().isoformat() if p.opened_at else None,
        })
    farms = {f.id: f for f in db.scalars(select(Farm)).all()}
    alerts = [
        {"lat": farms[a.farm_id].lat, "lon": farms[a.farm_id].lon, "district": farms[a.farm_id].district,
         "target": a.target, "name": tr(kb.targets[a.target]["names"], lang), "level": a.level,
         "trigger": a.trigger}
        for a in db.scalars(select(Alert).where(Alert.outcome.is_(None),
                                                Alert.issued_on >= date.today() - timedelta(days=7))).all()
    ]
    return {"points": points, "active_alerts": alerts, "radius_km": services.SPREAD_RADIUS_KM}


@router.get("/rainfall")
def rainfall():
    normals = services.rainfall_normals()
    out = []
    for sub, (place, lat, lon) in SUBDIVISION_POINTS.items():
        rc = services.rain_vs_normal(place, lat, lon)
        out.append({
            "subdivision": sub, "reference_place": place,
            "jjas_normal_mm": normals["subdivisions"][sub]["mean"]["jjas"],
            "current_month": rc,
            "jjas_series": normals["jjas_series"].get(sub, []),
        })
    return {"source": normals["_source"], "subdivisions": out}


@router.get("/pesticides")
def pesticide_baseline(state: str = "Maharashtra"):
    """State pesticide consumption (MoSPI ENVSTATS / DPPQS), the baseline that
    'more targeted pesticide use' is measured against."""
    path = services.KB_DIR / "mospi_pesticides.json"
    if not path.exists():
        return {"available": False}
    data = json.loads(path.read_text())
    states = data["states"]
    india: dict[str, float] = defaultdict(float)
    for s in states.values():
        for year, v in s.get("chemical", []):
            india[year] += v
    mine = states.get(state, {})
    chem = mine.get("chemical", [])
    latest = chem[-1] if chem else None
    ranking = sorted(
        ((name, s["chemical"][-1][1]) for name, s in states.items() if s.get("chemical")),
        key=lambda kv: -kv[1],
    )
    return {
        "available": True,
        "state": state,
        "source": data["_source"],
        "unit_note": data["_unit_note"],
        "chemical": chem,
        "bio": mine.get("bio", []),
        "india_chemical": sorted(india.items()),
        "latest_share_pct": round(100 * latest[1] / india[latest[0]], 1) if latest and india[latest[0]] else None,
        "rank": next((i + 1 for i, (n, _) in enumerate(ranking) if n == state), None),
        "states_ranked": len(ranking),
    }


@router.get("/outlook")
def risk_outlook(lang: str = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    """Where each pest/disease is building, for planning preventive action:
    open alerts from the last 7 days grouped by target."""
    since = date.today() - timedelta(days=7)
    farms = {f.id: f for f in db.scalars(select(Farm)).all()}
    groups: dict[str, dict] = {}
    for a in db.scalars(select(Alert).where(Alert.issued_on >= since)).all():
        g = groups.setdefault(a.target, {
            "target": a.target, "name": tr(kb.targets[a.target]["names"], lang),
            "crop": kb.targets[a.target]["crop"], "farms": set(), "districts": set(),
            "high": 0, "triggers": Counter(), "found": 0, "inspected": 0,
        })
        g["farms"].add(a.farm_id)
        g["districts"].add(farms[a.farm_id].district)
        g["high"] += a.level == "high"
        g["triggers"][a.trigger] += 1
        if a.outcome in ("found", "nothing_found"):
            g["inspected"] += 1
            g["found"] += a.outcome == "found"
    rows = [
        {**g, "farms": len(g["farms"]), "districts": sorted(g["districts"]), "triggers": dict(g["triggers"]),
         # What to stock: ICAR biocontrols/varieties/lures for this target. Some
         # (NRRI Tricho-cards) need a 45-day indent, so the outlook is when to order.
         "icar_inputs": [kb.tech_view(x, lang) for x in kb.technologies_for(target=g["target"])
                         if x["type"] in ("biocontrol", "variety", "monitoring")]}
        for g in groups.values()
    ]
    return sorted(rows, key=lambda r: (-r["high"], -r["farms"]))


@router.get("/kcc")
def kcc(month: int | None = None, kb: KB = Depends(get_kb)):
    """When and where farmers call the Kisan Call Centre about each pest group —
    an independent check on the risk calendar, and where to expect calls."""
    data = services.kcc_signals()
    if not data:
        return {"available": False}
    m = month or date.today().month
    groups = []
    for g in data["groups"]:
        names = [tr(kb.targets[t]["names"], "en") for t in g["targets"] if t in kb.targets]
        groups.append({k: g[k] for k in ("id", "crop", "label", "calls", "month_share", "peak_months", "by_year")}
                      | {"targets": g["targets"], "target_names": names, "top_districts": g["top_districts"][:5],
                         "expected_this_month": round(g["calls"] * g["month_share"][str(m)]
                                                      / max(1, data["years"][1] - data["years"][0] + 1))})
    groups.sort(key=lambda g: -g["expected_this_month"])
    return {"available": True, "month": m, "note": data["_note"], "source": data["source"], "years": data["years"],
            "coverage": data["coverage"], "groups": groups}


@router.get("/model")
def model_card():
    """Test-set report of the deployed model, straight from ml/artifacts/meta.json."""
    status = vision.model_status()
    meta_path = vision.ARTIFACTS / "meta.json"
    if status["is_stub"] or not meta_path.exists():
        return {"is_stub": True, "model_version": status["model_version"]}
    meta = json.loads(meta_path.read_text())
    keep = ("model_version", "backbone", "head", "img_size", "classes", "temperature", "trained_at",
            "dataset", "split", "test", "gate_on_test", "benchmark", "quick")
    return {"is_stub": False, **{k: meta.get(k) for k in keep}}


@router.post("/risk/run-all")
def run_all(db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    results = [services.run_risk(db, kb, f) for f in db.scalars(select(Farm)).all()]
    return {"farms": len(results), "alerts_issued": sum(len(r["issued"]) for r in results),
            "weather_sources": dict(Counter(r["weather_source"] for r in results))}
