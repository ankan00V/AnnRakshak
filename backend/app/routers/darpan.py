"""Darpan, the district's assistant (app/darpan.py).

  GET  /api/darpan/hello    the greeting and the questions worth starting from
  POST /api/darpan/ask      {text} -> lines built from this district's own rows

Officials only, and verified ones: Krishi is the farmers' helper and is not
touched by anything here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, darpan
from app.db import get_db
from app.kb import KB, get_kb
from app.limits import limit

router = APIRouter(prefix="/api/darpan", tags=["darpan"],
                   dependencies=[Depends(auth.require("expert")), Depends(auth.require_verified)])


@router.get("/hello")
def hello(request: Request, db: Session = Depends(get_db)):
    me = auth.current_user(request, db)
    if me is not None and me.is_demo:  # the register message, and no questions to tap
        return {"greeting": " ".join(_demo_lines(me)), "suggestions": []}
    return darpan.hello(db, me, demo=bool(me and me.is_demo))


def _demo_lines(me) -> list[str]:
    first = (me.name or "").split()
    name = f", {first[0]}" if first and first[0].lower() != "demo" else ""
    return [f"Namaste{name}! This is a demo account, so Darpan does not answer questions here.",
            "Register as an officer to ask about your own district: its cases, pests, officers and advisories."]


class AskIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)


@router.post("/ask")
def ask(body: AskIn, request: Request, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    me = auth.current_user(request, db)
    # The model call behind an unmatched question costs money and time.
    limit(f"darpan:{me.id if me else 'anon'}", 60, 60)
    if me is not None and me.is_demo:
        # Someone looking around: a greeting and the way to a real account,
        # rather than answers from seeded districts passed off as theirs.
        return {"intent": "demo", "asked": body.text, "lines": _demo_lines(me),
                "go": [{"label": "Register as an officer", "to": "/signup/expert"}]}
    return darpan.answer(db, kb, text=body.text, demo=bool(me and me.is_demo), officer=me)
