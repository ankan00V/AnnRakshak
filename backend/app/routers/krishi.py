"""Krishi, the in-app helper (app/krishi.py).

  GET  /api/krishi/hello?lang=&screen=     greeting and suggested questions for this screen
  POST /api/krishi/ask                     {text | topic, lang, screen, farm_id?} -> an answer

Open to signed-out visitors too (the login and sign-up screens have Krishi).
Answers about a farm's own weather or cases need a farm the caller may open.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, krishi
from app.db import get_db
from app.i18n import LANGS
from app.kb import KB, get_kb
from app.limits import client_ip, limit
from app.models import Farm

router = APIRouter(prefix="/api/krishi", tags=["krishi"])


def _lang(lang: str) -> str:
    return lang if lang in LANGS else "en"


@router.get("/hello")
def hello(request: Request, lang: str = "en", screen: str | None = None, db: Session = Depends(get_db)):
    user = auth.current_user(request, db)
    return krishi.hello(screen, _lang(lang), user.name if user else None)


class AskIn(BaseModel):
    text: str | None = Field(default=None, max_length=300)
    topic: str | None = Field(default=None, max_length=40)
    lang: str = "en"
    screen: str | None = Field(default=None, max_length=20)
    farm_id: int | None = None


@router.post("/ask")
def ask(body: AskIn, request: Request, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    limit(f"krishi:{client_ip(request)}", 60, 60)
    user = auth.current_user(request, db)
    farm = db.get(Farm, body.farm_id) if body.farm_id is not None else None
    if farm is not None and not auth.can_open_farm(user, farm):
        farm = None  # not theirs: answer as if no farm is open
    # Krishi is a personal assistant once signed in, so the fields it may talk
    # about are read from the session, never from the request. body.farm_id only
    # says which field the farmer is looking at; it can never widen what Krishi
    # can see, and an expert gets no personal answer at all.
    farms: list[Farm] = []
    if user is not None and user.role == "farmer":
        # Their own fields, and for a demo account the seeded demo ones — the
        # same rule as auth.can_open_farm. Written as a query rather than reusing
        # auth.farm_ids_for because that returns "all farms" when AUTH_ENFORCE is
        # off, and a personal answer must never widen to another farmer's rows,
        # whatever a deployment flag says.
        owned = Farm.user_id == user.id
        where = (owned | Farm.is_demo.is_(True)) if user.is_demo else owned
        farms = list(db.scalars(select(Farm).where(where).order_by(Farm.id)).all())
    return krishi.answer(db, kb, text=body.text, topic=body.topic, screen=body.screen, lang=_lang(body.lang),
                         farm=farm, user=user if user and user.role == "farmer" else None, farms=farms)
