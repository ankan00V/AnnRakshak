"""What a farmer may take away, and what they may have erased.

A farmer gave this app their name, their phone number, the corner of the
village their field sits in, and photographs of their crop. India's Digital
Personal Data Protection Act gives them the right to see all of it and the
right to have it erased, and an app that asks for consent at sign-up and
offers no way out of it is not keeping the bargain it made.

Erasure here means two different things, deliberately:

  The person goes.   Name, phone, email, village, the field's coordinates, the
                     sessions, the push subscriptions, the record of every
                     email we sent them, and every photograph they uploaded —
                     the files, not only the rows.

  The disease stays. A confirmed case of bacterial blight in Bhandara in
                     September is a public-health fact about a district, not a
                     fact about a person. The case keeps its crop, its date and
                     its district; it loses the farm, the name and the picture.
                     That is the anonymisation the Act contemplates, and it is
                     why the surveillance map does not develop holes every time
                     somebody leaves.

Both are offered to the farmer in their own account, and both are logged.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.models import (
    Advisory,
    Alert,
    Case,
    Diagnosis,
    EmailLog,
    Farm,
    FarmerProfile,
    FollowUp,
    LiveScan,
    Notice,
    Observation,
    OtpChallenge,
    Problem,
    PushSubscription,
    SensorReading,
    SprayLog,
    TrapReading,
    User,
    UserSession,
)


def _farms(db: Session, user: User) -> list[Farm]:
    return list(db.scalars(select(Farm).where(Farm.user_id == user.id)).all())


def export_account(db: Session, user: User) -> dict:
    """Everything this account holds, in one readable file.

    Written for the farmer who asked for it rather than for a machine: the
    fields are the ones they gave or were shown, with the words they were
    shown them in."""
    profile = db.get(FarmerProfile, user.id)
    farms = _farms(db, user)
    farm_ids = [f.id for f in farms]
    problems = list(db.scalars(select(Problem).where(Problem.farm_id.in_(farm_ids))).all()) if farm_ids else []
    problem_ids = [p.id for p in problems]

    def rows(model, where):
        return list(db.scalars(select(model).where(where)).all()) if farm_ids else []

    return {
        "exported_at": datetime.now().isoformat(),
        "account": {"name": user.name, "phone": user.phone, "email": user.email,
                    "role": user.role, "language": user.lang,
                    "joined": user.created_at.isoformat() if getattr(user, "created_at", None) else None},
        "profile": {"district": profile.district, "taluka": profile.taluka, "village": profile.village,
                    "total_land_acres": profile.total_land_acres,
                    "consent_given_at": profile.consent_at.isoformat() if profile.consent_at else None}
        if profile else None,
        "farms": [{"id": f.id, "crop": f.crop, "variety": f.variety, "area_acres": f.area_acres,
                   "sowing_date": f.sowing_date.isoformat() if f.sowing_date else None,
                   "district": f.district, "village": f.village,
                   "location": {"lat": f.lat, "lon": f.lon}} for f in farms],
        "problems": [{"id": p.id, "farm_id": p.farm_id, "target": p.target, "status": p.status,
                      "opened": p.opened_at.isoformat() if p.opened_at else None} for p in problems],
        "photographs": [{"problem_id": d.problem_id, "file": d.image_path,
                         "what_the_app_said": d.gate_outcome, "why": d.gate_reason}
                        for d in (db.scalars(select(Diagnosis)
                                             .where(Diagnosis.problem_id.in_(problem_ids))).all()
                                  if problem_ids else [])],
        "alerts": [{"target": a.target, "level": a.level, "issued_on": a.issued_on.isoformat(),
                    "what_you_found": a.outcome} for a in rows(Alert, Alert.farm_id.in_(farm_ids))],
        "sprays": [{"product": s.product, "at": s.sprayed_at.isoformat() if s.sprayed_at else None}
                   for s in rows(SprayLog, SprayLog.farm_id.in_(farm_ids))],
        "emails_we_sent": [{"kind": e.kind, "subject": e.subject,
                            "at": e.sent_at.isoformat() if e.sent_at else None}
                           for e in rows(EmailLog, EmailLog.farm_id.in_(farm_ids))],
    }


def erase_account(db: Session, user: User) -> dict:
    """Erase the person. Keep the district's disease record, with nobody in it.

    Returns what was removed, so the farmer is told rather than reassured."""
    farms = _farms(db, user)
    farm_ids = [f.id for f in farms]
    problem_ids = list(db.scalars(select(Problem.id).where(Problem.farm_id.in_(farm_ids))).all()) \
        if farm_ids else []

    photos = 0
    if problem_ids:
        for d in db.scalars(select(Diagnosis).where(Diagnosis.problem_id.in_(problem_ids))).all():
            if d.image_path:
                path = UPLOAD_DIR / d.image_path
                path.unlink(missing_ok=True)          # the file, not only the row
                d.image_path = None
                photos += 1
            d.topk = []       # the model's ranked guesses about this field

    # Everything that is about the person or their doorstep rather than about a
    # disease in a district.
    for model, where in (
        (Observation, Observation.problem_id.in_(problem_ids) if problem_ids else None),
        (LiveScan, LiveScan.farm_id.in_(farm_ids) if farm_ids else None),
        (Notice, Notice.farm_id.in_(farm_ids) if farm_ids else None),
        (PushSubscription, PushSubscription.farm_id.in_(farm_ids) if farm_ids else None),
        (EmailLog, EmailLog.farm_id.in_(farm_ids) if farm_ids else None),
        (SprayLog, SprayLog.farm_id.in_(farm_ids) if farm_ids else None),
        (SensorReading, SensorReading.farm_id.in_(farm_ids) if farm_ids else None),
        (TrapReading, TrapReading.farm_id.in_(farm_ids) if farm_ids else None),
        (FollowUp, FollowUp.problem_id.in_(problem_ids) if problem_ids else None),
        (Advisory, Advisory.problem_id.in_(problem_ids) if problem_ids else None),
        (UserSession, UserSession.user_id == user.id),
        # A one-time code is keyed by where it was sent, not by who it was for.
        (OtpChallenge, OtpChallenge.destination.in_([x for x in (user.email, user.phone) if x])),
    ):
        if where is None:
            continue
        for row in db.scalars(select(model).where(where)).all():
            db.delete(row)

    # The farm itself stops being a place: the district stays, because that is
    # what a hotspot is counted in; the corner of the village does not.
    for farm in farms:
        farm.user_id = None
        farm.farmer_name = "(erased)"
        farm.phone = farm.email = farm.email_token = None
        farm.village = farm.taluka = None
        farm.lat, farm.lon = round(farm.lat, 1), round(farm.lon, 1)   # ~11 km: a district, not a doorstep

    # An open case cannot be worked on by an officer any more: there is nobody
    # to tell the answer to.
    if problem_ids:
        for case in db.scalars(select(Case).where(Case.problem_id.in_(problem_ids),
                                                  Case.status == "open")).all():
            case.status = "resolved"
            case.resolved_at = datetime.now()

    profile = db.get(FarmerProfile, user.id)
    if profile is not None:
        db.delete(profile)
    db.delete(user)
    db.commit()
    return {"farms": len(farms), "problems": len(problem_ids), "photographs": photos}
