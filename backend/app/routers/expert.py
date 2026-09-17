"""Agronomist / extension-officer queue: pre-packed case bundles, one-screen
decisions. Every verdict becomes a labelled field confirmation."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, services
from app.db import get_db
from app.kb import KB, get_kb
from app.models import Case, Farm, Problem

router = APIRouter(prefix="/api/cases", tags=["expert"], dependencies=[Depends(auth.require("expert"))])


@router.get("")
def list_cases(status: Literal["open", "resolved", "all"] = "open", lang: str = "en",
               db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    q = select(Case).order_by(Case.id)
    if status != "all":
        q = q.where(Case.status == status)
    out = []
    for c in db.scalars(q).all():
        problem = db.get(Problem, c.problem_id)
        farm: Farm = problem.farm
        last = problem.diagnoses[-1] if problem.diagnoses else None
        top = last.topk[0] if last and last.topk else None
        out.append(services.case_brief(db, c) | {
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "farm_id": farm.id, "farmer_name": farm.farmer_name, "district": farm.district,
            "crop": farm.crop, "severity": problem.severity,
            "photo": services._image_url(last.image_path) if last else None,
            "model_top": services._pred_view(kb, services.gate.Prediction(top["target"], top["confidence"]), lang)
            if top else None,
            "is_stub": last.is_stub if last else None,
        })
    return out


@router.get("/{case_id}")
def get_case(case_id: int, lang: str = "en", db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    return services.case_bundle(db, kb, case, lang)


class ResolveIn(BaseModel):
    verdict: Literal["confirmed", "corrected"]
    final_label: str
    expert_name: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)
    referred_to_lab: bool = False


@router.post("/{case_id}/resolve")
def resolve(case_id: int, body: ResolveIn, request: Request, db: Session = Depends(get_db),
            kb: KB = Depends(get_kb)):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    verdict = body.model_dump()
    expert = auth.current_user(request, db)
    if expert is not None:  # signed in: the verdict carries who gave it, not a typed name
        verdict["expert_name"] = expert.name[:80]
    try:
        return services.resolve_case(db, kb, case, **verdict)
    except ValueError as exc:
        raise HTTPException(409 if "already" in str(exc) else 422, str(exc)) from exc
