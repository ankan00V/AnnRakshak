"""What the district office does, as opposed to what it looks at.

Maharashtra has run pest surveillance this way since 2009-10 (CROPSAP, with
NCIPM): scouts sample fixed plots, the data is fed in, and then an officer
**issues a location-specific advisory** that reaches registered farmers. The
dashboard had the looking and not the doing; this module is the doing.

Four levers:

  * issue an advisory — tell every farm of one crop in chosen districts what is
    building and what to check, in their own language;
  * ask for an inspection — the same machinery, worded as a check rather than a
    warning, for a block a scout should walk;
  * verify an officer — until the district office says so, a sign-up reviews
    nothing and is handed no cases;
  * plan the indent — what to stock, from what is building, with the lead time
    an ICAR bio-input actually needs.

An advisory reaches farmers, so nothing here invents agronomy: the wording is
the knowledge base's own, the officer adds a note in their words, and every
issue is recorded against the name that issued it.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.kb import KB, tr
from app.models import (
    Advisory,
    Alert,
    Case,
    Confirmation,
    ExpertProfile,
    Farm,
    OfficerAction,
    OfficerAdvisory,
    Problem,
    User,
)

ADVISORY_REASON = {
    "advisory": {
        "en": "{officer} of the district agriculture office reports {name} building in {district}. Check your field.",
        "hi": "जिला कृषि कार्यालय के {officer} ने {district} में {name} बढ़ने की सूचना दी है। अपना खेत जाँचें।",
        "mr": "जिल्हा कृषी कार्यालयाचे {officer} यांनी {district} मध्ये {name} वाढत असल्याचे कळवले आहे. तुमचे शेत तपासा.",
    },
    "inspection": {
        "en": "{officer} has asked for this field to be checked for {name}.",
        "hi": "{officer} ने इस खेत में {name} की जाँच करने को कहा है।",
        "mr": "{officer} यांनी या शेतात {name} ची तपासणी करण्यास सांगितले आहे.",
    },
}

NOTE = {"en": " Officer's note: {note}", "hi": " अधिकारी की टिप्पणी: {note}",
        "mr": " अधिकाऱ्याची टिप्पणी: {note}"}

LANGS = ("en", "hi", "mr")

MAX_FARMS_PER_ISSUE = 5000
"""A single advisory cannot quietly become a state-wide broadcast."""


def targets_for(kb: KB, crop: str) -> list[dict]:
    """What an officer may issue an advisory about: this crop's own problems."""
    return [kb.target_view(t, "en") for t, v in kb.targets.items() if v["crop"] == crop]


def farms_matching(db: Session, *, crop: str, districts: list[str], demo: bool) -> list[Farm]:
    """Every farm the advisory would reach. Demo and real never mix, here least
    of all: this sends a message to a person."""
    q = select(Farm).where(Farm.crop == crop, Farm.is_demo.is_(demo))
    if districts:
        q = q.where(Farm.district.in_(districts))
    return list(db.scalars(q).all())


def preview(db: Session, kb: KB, *, target: str, crop: str, districts: list[str],
            kind: str, note: str | None, officer: str, demo: bool) -> dict:
    """What would be sent, to how many, in every language — before it is sent."""
    farms = farms_matching(db, crop=crop, districts=districts, demo=demo)
    rule = kb.rules.get(target, {})
    names = kb.targets[target]["names"]
    where = ", ".join(districts) if districts else "your district"
    reason = {
        lang: tr(ADVISORY_REASON[kind], lang).format(
            officer=officer, name=tr(names, lang), district=where)
        + (tr(NOTE, lang).format(note=note) if note else "")
        for lang in LANGS
    }
    return {
        "target": target, "name": tr(names, "en"), "crop": crop, "kind": kind,
        "districts": districts, "farms": len(farms),
        "over_limit": len(farms) > MAX_FARMS_PER_ISSUE,
        "reason": reason,
        "tasks": rule.get("tasks") or {},
        "by_district": dict(sorted(_count_by_district(farms).items())),
    }


def _count_by_district(farms: list[Farm]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in farms:
        out[f.district] = out.get(f.district, 0) + 1
    return out


def issue(db: Session, kb: KB, *, target: str, crop: str, districts: list[str], kind: str,
          level: str, note: str | None, officer: User, demo: bool,
          today: date | None = None) -> dict:
    """Send it. One alert per farm, skipping any farm that already has this
    officer advisory today, so a double click does not double the message."""
    if kind not in ADVISORY_REASON:
        raise ValueError("kind must be 'advisory' or 'inspection'")
    if target not in kb.targets:
        raise ValueError(f"{target} is not a known target")
    if kb.targets[target]["crop"] != crop:
        raise ValueError(f"{target} is not a {crop} problem")
    rule = kb.rules.get(target, {})
    if not (rule.get("tasks") or {}).get("en"):
        raise ValueError("no inspection tasks are authored for this target")

    today = today or date.today()
    view = preview(db, kb, target=target, crop=crop, districts=districts, kind=kind,
                   note=note, officer=officer.name, demo=demo)
    if view["over_limit"]:
        raise ValueError(f"{view['farms']} farms is more than one advisory may reach")

    farms = farms_matching(db, crop=crop, districts=districts, demo=demo)
    trigger = "officer" if kind == "advisory" else "inspection"
    already = {
        fid for (fid,) in db.execute(
            select(Alert.farm_id).where(
                Alert.target == target, Alert.trigger == trigger, Alert.issued_on == today,
                Alert.farm_id.in_([f.id for f in farms]))
        ).all()
    }
    sent = 0
    for farm in farms:
        if farm.id in already:
            continue
        db.add(Alert(farm_id=farm.id, target=target, trigger=trigger, level=level,
                     reason=view["reason"], tasks=rule["tasks"], issued_on=today))
        sent += 1

    row = OfficerAdvisory(
        issued_by=officer.id, issued_at=datetime.now(UTC), target=target, crop=crop,
        districts=districts, kind=kind, level=level, note=note, farms=sent, is_demo=demo,
    )
    db.add(row)
    db.flush()
    record(db, actor=officer, action=f"issue_{kind}", subject="advisory", subject_id=row.id,
           detail={"target": target, "districts": districts, "farms": sent})
    db.commit()
    return {"id": row.id, "sent": sent, "skipped": len(farms) - sent,
            "districts": districts, "target": target, "kind": kind}


def history(db: Session, *, demo: bool, limit: int = 40) -> list[dict]:
    """What the office has issued, most recent first — and what came back.

    An advisory that nobody acts on is worth knowing about: the alerts it
    created carry the farmer's answer, so each row can say how many went and
    looked and how many found the thing. That is the only honest measure of
    whether sending it was worth anything."""
    rows = db.execute(
        select(OfficerAdvisory, User.name)
        .join(User, User.id == OfficerAdvisory.issued_by)
        .where(OfficerAdvisory.is_demo.is_(demo))
        .order_by(OfficerAdvisory.id.desc()).limit(limit)
    ).all()
    if not rows:
        return []

    # One query for every outcome behind these advisories, matched on what the
    # issue actually created: same target, same trigger, same day.
    keys = {(a.target, "officer" if a.kind == "advisory" else "inspection",
             a.issued_at.date() if a.issued_at else None) for a, _ in rows}
    counts: dict[tuple, Counter] = {}
    for target, trigger, day in keys:
        if day is None:
            continue
        outcomes = db.execute(
            select(Alert.outcome, func.count(Alert.id))
            .join(Farm, Farm.id == Alert.farm_id)
            .where(Alert.target == target, Alert.trigger == trigger, Alert.issued_on == day,
                   Farm.is_demo.is_(demo))
            .group_by(Alert.outcome)
        ).all()
        counts[(target, trigger, day)] = Counter({o: n for o, n in outcomes})

    out = []
    for a, name in rows:
        day = a.issued_at.date() if a.issued_at else None
        c = counts.get((a.target, "officer" if a.kind == "advisory" else "inspection", day), Counter())
        inspected = c.get("found", 0) + c.get("nothing_found", 0)
        out.append({
            "id": a.id, "issued_by": name, "issued_at": a.issued_at.isoformat() if a.issued_at else None,
            "target": a.target, "crop": a.crop, "districts": a.districts or [], "kind": a.kind,
            "level": a.level, "note": a.note, "farms": a.farms,
            "inspected": inspected, "found": c.get("found", 0),
            "still_waiting": max(a.farms - inspected, 0),
        })
    return out


# --------------------------------------------------------------------------
# Officers waiting to be let in
# --------------------------------------------------------------------------

def pending_officers(db: Session, *, demo: bool) -> list[dict]:
    """Sign-ups the district office has not verified. Until it does, they review
    nothing and are handed no cases."""
    rows = db.execute(
        select(User, ExpertProfile)
        .join(ExpertProfile, ExpertProfile.user_id == User.id)
        .where(User.role == "expert", ExpertProfile.verified.is_(False), User.is_demo.is_(demo))
        .order_by(User.id.desc())
    ).all()
    return [{
        "user_id": u.id, "name": u.name, "email": u.email, "phone": u.phone,
        "designation": p.designation, "organisation": p.organisation, "employee_id": p.employee_id,
        "qualification": p.qualification, "experience_years": p.experience_years,
        "districts": p.districts or [], "crops": p.crops or [],
        "joined": u.created_at.isoformat() if getattr(u, "created_at", None) else None,
    } for u, p in rows]


def record(db: Session, *, actor: User | None, action: str, subject: str | None = None,
           subject_id: int | None = None, detail: dict | None = None) -> None:
    """Write one line into the office's own record of who did what.

    Flushed with the change it describes, so an action and its audit line are
    the same transaction: there is no state where one exists without the other."""
    db.add(OfficerAction(
        actor_id=actor.id if actor else None,
        actor_name=actor.name if actor else "system",
        action=action, subject=subject, subject_id=subject_id, detail=detail,
        at=datetime.now(UTC), is_demo=bool(actor and actor.is_demo),
    ))
    db.flush()


def actions(db: Session, *, demo: bool, limit: int = 60) -> list[dict]:
    """The office's record, most recent first."""
    rows = db.scalars(
        select(OfficerAction).where(OfficerAction.is_demo.is_(demo))
        .order_by(OfficerAction.id.desc()).limit(limit)
    ).all()
    return [{"id": a.id, "actor": a.actor_name, "action": a.action, "subject": a.subject,
             "subject_id": a.subject_id, "detail": a.detail or {},
             "at": a.at.isoformat() if a.at else None} for a in rows]


def set_verified(db: Session, user_id: int, verified: bool, *, by: User | None = None) -> dict:
    """Let an officer in, or take the badge back.

    Never yourself: an officer who can verify their own account has not been
    verified by anybody. Never across the demo line either — a showcase
    supervisor has no business over a real district's staff."""
    profile = db.get(ExpertProfile, user_id)
    if profile is None:
        raise ValueError("not an officer")
    if by is not None and by.id == user_id:
        raise ValueError("an officer cannot verify their own account")
    subject = db.get(User, user_id)
    if by is not None and subject is not None and subject.is_demo != by.is_demo:
        raise ValueError("not an officer")   # same answer as an id that is not there
    profile.verified = verified
    record(db, actor=by, action="verify_officer" if verified else "unverify_officer",
           subject="officer", subject_id=user_id,
           detail={"name": subject.name if subject else None})
    db.commit()
    return {"user_id": user_id, "verified": verified}


# --------------------------------------------------------------------------
# What the model cannot name yet
# --------------------------------------------------------------------------

def gaps(db: Session, *, demo: bool, limit: int = 50) -> list[dict]:
    """Every case an officer closed as 'something else'. This is the training
    backlog, in the officers' own words: a problem seen in the field often
    enough here should become a class the model knows."""
    rows = db.execute(
        select(Confirmation, Farm.district, Farm.crop)
        .join(Problem, Problem.id == Confirmation.problem_id)
        .join(Farm, Farm.id == Problem.farm_id)
        .where(Confirmation.final_label == "other", Farm.is_demo.is_(demo))
        .order_by(Confirmation.id.desc()).limit(limit)
    ).all()
    return [{
        "id": c.id, "on": c.created_at.date().isoformat() if c.created_at else None,
        "district": district, "crop": crop, "model_label": c.model_label,
        "expert": c.expert_name, "note": c.notes, "referred_to_lab": c.referred_to_lab,
    } for c, district, crop in rows]


# --------------------------------------------------------------------------
# What to order, and when
# --------------------------------------------------------------------------

LEAD_DAYS = 45
"""NRRI Tricho-cards are reared to order. Ordering when the damage shows is
ordering six weeks late, which is why the outlook is a procurement screen."""


def indent(db: Session, kb: KB, *, demo: bool, days: int = 7, lang: str = "en") -> list[dict]:
    """One row per problem building: how many farms, in which districts, and the
    ICAR inputs to stock for it."""
    since = date.today() - timedelta(days=days)
    farms = {f.id: f for f in db.scalars(select(Farm).where(Farm.is_demo.is_(demo))).all()}
    groups: dict[str, dict] = {}
    for a in db.scalars(select(Alert).where(Alert.issued_on >= since)).all():
        farm = farms.get(a.farm_id)
        if farm is None:
            continue
        g = groups.setdefault(a.target, {
            "target": a.target, "name": tr(kb.targets[a.target]["names"], lang),
            "crop": kb.targets[a.target]["crop"], "farm_ids": set(), "districts": set(),
            "high": 0, "acres": 0.0,
        })
        if farm.id not in g["farm_ids"]:
            g["acres"] += farm.area_acres or 0
        g["farm_ids"].add(farm.id)
        g["districts"].add(farm.district)
        g["high"] += a.level == "high"

    out = []
    for g in groups.values():
        inputs = [kb.tech_view(x, lang) for x in kb.technologies_for(target=g["target"])
                  if x["type"] in ("biocontrol", "variety", "monitoring")]
        out.append({
            "target": g["target"], "name": g["name"], "crop": g["crop"],
            "farms": len(g["farm_ids"]), "acres": round(g["acres"], 1),
            "districts": sorted(g["districts"]), "high": g["high"],
            "inputs": inputs,
            # Tricho-cards are quoted per acre; the rest is a count of farms to
            # supply. Both are a starting quantity for the office, not a bill.
            "suggested": [{"input": i["short"], "institute": _institute_name(i),
                           "quantity": f"{round(g['acres'])} acre-sets" if "tricho" in i["short"].lower()
                           else f"{len(g['farm_ids'])} units",
                           "order_by": (date.today() + timedelta(days=LEAD_DAYS)).isoformat()
                           if "tricho" in i["short"].lower() else None}
                          for i in inputs],
        })
    return sorted(out, key=lambda r: (-r["high"], -r["farms"]))


def _institute_name(tech: dict) -> str | None:
    """tech_view carries the whole institute record; a plan only needs the name
    to print and to put in a CSV cell."""
    inst = tech.get("institute")
    if isinstance(inst, dict):
        return inst.get("name") or inst.get("id")
    return inst


def indent_csv(rows: list[dict]) -> str:
    """The same table as a file the office can attach to an indent."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Problem", "Crop", "Farms", "Acres", "Districts", "High alerts",
                "Input", "Institute", "Suggested quantity", "Order by"])
    for r in rows:
        if not r["suggested"]:
            w.writerow([r["name"], r["crop"], r["farms"], r["acres"], "; ".join(r["districts"]),
                        r["high"], "", "", "", ""])
        for s in r["suggested"]:
            w.writerow([r["name"], r["crop"], r["farms"], r["acres"], "; ".join(r["districts"]),
                        r["high"], s["input"], s.get("institute") or "", s["quantity"],
                        s.get("order_by") or ""])
    return buf.getvalue()


# --------------------------------------------------------------------------
# One farm, everything the office knows about it
# --------------------------------------------------------------------------

def farm_dossier(db: Session, kb: KB, farm: Farm, lang: str = "en") -> dict:
    """What an officer needs before ringing a farmer or sending a scout: the
    field, what has been found on it, what it has been warned about, and
    whether anybody went and looked."""
    from app import services  # noqa: PLC0415  (services imports office's siblings)

    problems = db.scalars(
        select(Problem).where(Problem.farm_id == farm.id).order_by(Problem.id.desc())
    ).all()
    alerts = db.scalars(
        select(Alert).where(Alert.farm_id == farm.id).order_by(Alert.issued_on.desc(), Alert.id.desc())
    ).all()[:15]
    cases = db.execute(
        select(Case, Problem.target)
        .join(Problem, Problem.id == Case.problem_id)
        .where(Problem.farm_id == farm.id).order_by(Case.id.desc())
    ).all()
    confirmations = db.scalars(
        select(Confirmation).join(Problem, Problem.id == Confirmation.problem_id)
        .where(Problem.farm_id == farm.id).order_by(Confirmation.id.desc())
    ).all()[:10]
    answered = [a for a in alerts if a.outcome in ("found", "nothing_found")]
    return {
        "farm": services.farm_view(kb, farm, lang),
        "open_problems": sum(1 for p in problems if p.status == "open"),
        "problems": [{"id": p.id, "target": p.target,
                      "name": tr(kb.targets[p.target]["names"], lang) if p.target in kb.targets else None,
                      "status": p.status, "severity": p.severity,
                      "opened": p.opened_at.date().isoformat() if p.opened_at else None}
                     for p in problems[:10]],
        "cases": [{"id": c.id, "status": c.status, "reason": c.reason, "target": target,
                   "assigned_to": c.assigned_to,
                   "created": c.created_at.isoformat() if c.created_at else None} for c, target in cases[:10]],
        "alerts": [{"id": a.id, "target": a.target,
                    "name": tr(kb.targets[a.target]["names"], lang) if a.target in kb.targets else a.target,
                    "level": a.level, "trigger": a.trigger, "issued_on": a.issued_on.isoformat(),
                    "outcome": a.outcome} for a in alerts],
        "inspection_rate": round(len(answered) / len(alerts), 2) if alerts else None,
        "found_rate": round(sum(1 for a in answered if a.outcome == "found") / len(answered), 2)
        if answered else None,
        "confirmations": [{"final_label": c.final_label, "verdict": c.verdict, "expert": c.expert_name,
                           "on": c.created_at.date().isoformat() if c.created_at else None,
                           "notes": c.notes} for c in confirmations],
    }


# --------------------------------------------------------------------------
# The worklist
# --------------------------------------------------------------------------

SLA_HOURS = 24
"""A farmer waiting longer than this for a person has waited too long."""


def worklist(db: Session, kb: KB, *, demo: bool, lang: str = "en") -> dict:
    """What needs a person today, in the order it should be dealt with."""
    now = datetime.now()
    cases = db.execute(
        select(Case, Farm.district)
        .join(Problem, Problem.id == Case.problem_id)
        .join(Farm, Farm.id == Problem.farm_id)
        .where(Case.status == "open", Farm.is_demo.is_(demo))
    ).all()
    overdue = [
        {"id": c.id, "district": district,
         "hours": round((now - c.created_at).total_seconds() / 3600, 1)}
        for c, district in cases
        if c.created_at and (now - c.created_at) > timedelta(hours=SLA_HOURS)
    ]
    unrouted = [c.id for c, _ in cases if c.assigned_to is None]

    since = date.today() - timedelta(days=7)
    building: dict[str, dict] = {}
    farm_ids = {f for (f,) in db.execute(
        select(Farm.id).where(Farm.is_demo.is_(demo))).all()}
    for a in db.scalars(select(Alert).where(
            Alert.issued_on >= since, Alert.level == "high", Alert.farm_id.in_(farm_ids))).all():
        g = building.setdefault(a.target, {"target": a.target,
                                           "name": tr(kb.targets[a.target]["names"], lang),
                                           "crop": kb.targets[a.target]["crop"], "farms": set()})
        g["farms"].add(a.farm_id)

    return {
        "overdue_cases": sorted(overdue, key=lambda r: -r["hours"])[:20],
        "overdue_count": len(overdue),
        "unrouted": unrouted,
        "pending_officers": len(pending_officers(db, demo=demo)),
        "building": sorted(
            [{"target": g["target"], "name": g["name"], "crop": g["crop"], "farms": len(g["farms"])}
             for g in building.values()], key=lambda r: -r["farms"])[:6],
        "unnamed_problems": db.scalar(
            select(func.count(Confirmation.id))
            .join(Problem, Problem.id == Confirmation.problem_id)
            .join(Farm, Farm.id == Problem.farm_id)
            .where(Confirmation.final_label == "other", Farm.is_demo.is_(demo))) or 0,
        "sla_hours": SLA_HOURS,
    }
