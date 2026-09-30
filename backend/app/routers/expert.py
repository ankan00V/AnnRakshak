"""Agronomist / extension-officer queue: pre-packed case bundles, one-screen
decisions. Every verdict becomes a labelled field confirmation."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app import auth, services
from app.db import get_db
from app.kb import KB, get_kb
from app.models import Case, Farm, Problem

router = APIRouter(prefix="/api/cases", tags=["expert"], dependencies=[Depends(auth.require("expert"))])


@router.get("")
def list_cases(status: Literal["open", "resolved", "all"] = "open",
               scope: Literal["mine", "all"] = "all", lang: str = "en",
               request: Request = None, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    """`scope=mine` is this officer's queue: the cases routed to them, plus any
    the router could not place, which stay everybody's to pick up."""
    me = auth.current_user(request, db)
    q = (select(Case).join(Problem, Problem.id == Case.problem_id)
         .join(Farm, Farm.id == Problem.farm_id).order_by(Case.id))
    if me is not None:
        # Showcase data and real farmers' fields never appear in the same queue.
        q = q.where(Farm.is_demo.is_(me.is_demo))
    if status != "all":
        q = q.where(Case.status == status)
    if scope == "mine":
        q = q.where(or_(Case.assigned_to == (me.id if me else None), Case.assigned_to.is_(None)))
    cases = db.scalars(q).all()
    # One trip for the briefs, one for the problems and their farms and photos:
    # the queue is read over a remote database, so per-case queries show.
    briefs = services.case_briefs(db, cases)
    problems = {
        p.id: p for p in db.scalars(
            select(Problem)
            .where(Problem.id.in_([c.problem_id for c in cases]))
            .options(joinedload(Problem.farm), selectinload(Problem.diagnoses))
        ).unique().all()
    } if cases else {}
    out = []
    for c in cases:
        problem = problems.get(c.problem_id)
        if problem is None:
            continue
        farm: Farm = problem.farm
        last = problem.diagnoses[-1] if problem.diagnoses else None
        top = last.topk[0] if last and last.topk else None
        out.append(briefs[c.id] | {
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "farm_id": farm.id, "farmer_name": farm.farmer_name, "district": farm.district,
            "crop": farm.crop, "severity": problem.severity,
            "photo": services._image_url(last.image_path) if last else None,
            "model_top": services._pred_view(kb, services.gate.Prediction(top["target"], top["confidence"]), lang)
            if top else None,
            "is_stub": last.is_stub if last else None,
        })
    return out


def _case_for(request: Request, db: Session, case_id: int) -> Case:
    """The case, if this account is allowed to see it. A demo reviewer asking
    for a real farmer's case is told the same thing as for an id that does not
    exist — it is not theirs to know about."""
    case = db.get(Case, case_id)
    if case is None or not services.case_is_visible_to(db, case, auth.current_user(request, db)):
        raise HTTPException(404, "case not found")
    return case


@router.get("/{case_id}")
def get_case(case_id: int, request: Request, lang: str = "en",
             db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    return services.case_bundle(db, kb, _case_for(request, db, case_id), lang)


class ReassignIn(BaseModel):
    to_user_id: int | None = None
    """None = let the router pick whoever is freest."""


@router.post("/{case_id}/reassign")
def reassign(case_id: int, body: ReassignIn, request: Request, db: Session = Depends(get_db)):
    """Hand a case on: wrong speciality, too long a queue, or off for the day."""
    case = _case_for(request, db, case_id)
    if case.status != "open":
        raise HTTPException(409, "case is already resolved")
    try:
        picked = services.reassign_case(db, case, body.to_user_id)
    except ValueError:
        raise HTTPException(400, "not an officer") from None
    db.commit()
    return services.case_brief(db, case) | {"assigned_to": picked}


@router.get("/officers/list")
def officers(request: Request, district: str | None = None, db: Session = Depends(get_db)):
    """Officers a case can be handed to, with what each is carrying."""
    me = auth.current_user(request, db)
    return services.workload(db, district, demo=bool(me and me.is_demo))


class ResolveIn(BaseModel):
    verdict: Literal["confirmed", "corrected"]
    final_label: str
    expert_name: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)
    referred_to_lab: bool = False


@router.post("/{case_id}/resolve")
def resolve(case_id: int, body: ResolveIn, request: Request, db: Session = Depends(get_db),
            kb: KB = Depends(get_kb)):
    case = _case_for(request, db, case_id)
    verdict = body.model_dump()
    expert = auth.current_user(request, db)
    if expert is not None:  # signed in: the verdict carries who gave it, not a typed name
        verdict["expert_name"] = expert.name[:80]
    try:
        return services.resolve_case(db, kb, case, **verdict)
    except ValueError as exc:
        raise HTTPException(409 if "already" in str(exc) else 422, str(exc)) from exc
