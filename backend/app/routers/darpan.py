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
    return darpan.hello(auth.current_user(request, db))


class AskIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)


@router.post("/ask")
def ask(body: AskIn, request: Request, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    me = auth.current_user(request, db)
    # The model call behind an unmatched question costs money and time.
    limit(f"darpan:{me.id if me else 'anon'}", 60, 60)
    return darpan.answer(db, kb, text=body.text, demo=bool(me and me.is_demo), officer=me)
