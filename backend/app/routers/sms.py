"""Replies by SMS, for the farmer whose phone runs no app.

  POST /api/sms/inbound            the provider's callback when somebody texts our number
  POST /api/sms/inbound/{secret}   the same, for a provider that cannot send a header

The day-four SMS asks how the crop is and says how to answer: 1 better, 2 the
same, 3 worse, or the same words in the farmer's language. A reply from a
field's phone is recorded exactly as the app's own Better / Same / Worse
buttons record it (services.respond_followup), so "worse" re-opens the case for
an expert. Without this the question reached the farmers least able to answer
it in the app and their answer went nowhere.

Who may call it. This URL is public, and a forged reply could close a farmer's
case or open a false one, so a request is taken only when it proves it came
from the provider: Twilio's signature (X-Twilio-Signature, keyed with
TWILIO_AUTH_TOKEN), or the shared secret SMS_INBOUND_SECRET — as the
X-AnnRakshak-Secret header, or as the last segment of the callback URL that was
registered with the provider. Neither configured, nothing is taken.

Never as a query parameter. A query string is written into every access log
between the provider and this process — the proxy's, the load balancer's,
uvicorn's — and a secret in a log is a secret anyone with the logs can use to
close a farmer's case. A path segment is too, so this module redacts it from
uvicorn's access log, and a `?key=` is refused outright so nobody registers one.

Everything that arrives is logged (sms_log) and answered with one line: a
thank-you for an answer, the options for anything we could not read, and the
options for a number we do not know, which is most often a farmer texting from
a family member's phone.

STOP turns a farmer's SMS alerts off and START turns them on again — the
profile screen's switch, for the farmer who has no profile screen.
"""

from __future__ import annotations

import hmac
import logging
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import auth, config, services, sms
from app.db import get_db
from app.kb import KB, get_kb
from app.limits import client_ip, limit
from app.models import Farm, FollowUp, Problem, User

router = APIRouter(prefix="/api/sms", tags=["sms"])
log = logging.getLogger("annrakshak.sms")

_IN_PATH = re.compile(r"(/api/sms/inbound/)[^/?\s\"]+")


class _HideInboundSecret(logging.Filter):
    """Takes the secret out of the callback URL before uvicorn's access log
    writes it down. The record's arguments are (client, method, path, version,
    status); the path is the only one rewritten, and nothing is ever dropped."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and any(isinstance(a, str) and "/api/sms/inbound/" in a for a in args):
            record.args = tuple(_IN_PATH.sub(r"\1[redacted]", a) if isinstance(a, str) else a for a in args)
        elif isinstance(record.msg, str) and "/api/sms/inbound/" in record.msg:
            record.msg = _IN_PATH.sub(r"\1[redacted]", record.msg)
        return True


logging.getLogger("uvicorn.access").addFilter(_HideInboundSecret())

SENDER_FIELDS = ("From", "from", "sender", "mobile", "msisdn", "number")
TEXT_FIELDS = ("Body", "body", "message", "text", "content", "sms")
"""What providers call the two fields: Twilio says From and Body, MSG91's
inbound numbers and most Indian long-code gateways one of the others."""


def _authentic(request: Request, params: dict[str, str], in_path: str | None = None) -> bool:
    if "key" in request.query_params:
        log.warning("sms inbound refused: a secret in the query string ends up in access logs; "
                    "send the X-AnnRakshak-Secret header or register /api/sms/inbound/<secret>")
        return False
    secret = config.SMS_INBOUND_SECRET
    given = in_path if in_path is not None else request.headers.get("x-annrakshak-secret", "")
    if secret and given and hmac.compare_digest(secret.encode(), given.encode()):
        return True
    signature = request.headers.get("x-twilio-signature")
    if signature and config.TWILIO_AUTH_TOKEN:
        # Signed over the URL Twilio was given, which is the public one: behind
        # a proxy this process sees http:// and an internal host instead.
        query = f"?{request.url.query}" if request.url.query else ""
        return sms.twilio_signature_ok(f"{config.PUBLIC_APP_URL}{request.url.path}{query}", params, signature)
    return False


def _pending(db: Session, farms: list[Farm]) -> FollowUp | None:
    """The question this reply answers: the open follow-up most recently asked
    on any of the number's fields — the one the farmer just read."""
    due = db.scalars(select(FollowUp).join(Problem, Problem.id == FollowUp.problem_id).where(
        Problem.farm_id.in_([f.id for f in farms]), FollowUp.response.is_(None),
        FollowUp.due_on <= date.today())).all()
    if not due:
        return None
    return max(due, key=lambda f: (f.reminded_at is not None, f.reminded_at or f.due_on, f.due_on, f.id))


def _reply(db: Session, number: str, text: str, farm_id: int | None) -> None:
    status, err = sms.send(number, sms.plain(text), kind="reply")
    sms.record(db, farm_id=farm_id, number=number, direction="out", kind="reply", status=status,
               body=text, error=err)


def handle(db: Session, kb: KB, number: str | None, text: str) -> dict:
    """Read one reply and act on it. Separate from the route so the work —
    which may open a case and route it to an officer — runs off the event loop."""
    farms = list(db.scalars(select(Farm).where(Farm.phone == number, Farm.is_demo.is_(False))).all()) \
        if number else []
    if not farms:
        sms.record(db, number=number or "", direction="in", kind="unknown", status="unknown", body=text[:80])
        if number:
            _reply(db, number, "AnnRakshak: " + sms.say("options", "en"), None)
        db.commit()
        return {"matched": False, "reason": "unknown sender"}

    owner = db.get(User, farms[0].user_id) if farms[0].user_id else None
    lang = (owner.lang if owner else None) or farms[0].lang or "en"

    switch = sms.parse_switch(text)
    if switch:
        # The same switch the profile screen offers, set where notify reads
        # it: on the person, and on any field with no account behind it.
        pref = "off" if switch == "off" else "warnings"
        for user_id in {f.user_id for f in farms if f.user_id}:
            db.get(User, user_id).sms_pref = pref
        for f in farms:
            if not f.user_id:
                f.sms_pref = pref
        sms.record(db, farm_id=farms[0].id, number=number, direction="in", kind="switch", status=switch,
                   body=text[:80])
        _reply(db, number, "AnnRakshak: " + sms.say("stopped" if switch == "off" else "started", lang),
               farms[0].id)
        db.commit()
        return {"matched": True, "sms_pref": pref}

    answer, note = sms.parse_reply(text)
    if answer is None:
        sms.record(db, farm_id=farms[0].id, number=number, direction="in", kind="unparsed", status="unparsed",
                   body=text[:80])
        _reply(db, number, "AnnRakshak: " + sms.say("options", lang), farms[0].id)
        db.commit()
        return {"matched": False, "reason": "could not read the answer"}

    fu = _pending(db, farms)
    if fu is None:
        sms.record(db, farm_id=farms[0].id, number=number, direction="in", kind="answer", status="nothing",
                   body=text[:80])
        _reply(db, number, sms.say("nothing_pending", lang), farms[0].id)
        db.commit()
        return {"matched": False, "reason": "no question waiting"}

    problem = db.get(Problem, fu.problem_id)
    sms.record(db, farm_id=problem.farm_id, number=number, direction="in", kind="answer", status="matched",
               ref=f"followup:{fu.id}", body=text[:80])
    # Exactly the app's own answer: resolved, asked again in four days, or —
    # for "worse" — escalated to an expert with the farmer's own words on it.
    out = services.respond_followup(db, kb, fu, answer, lang, note=note or None)
    thanks = sms.say(f"thanks_{answer}", lang, days=config.FOLLOWUP_DUE_DAYS)
    _reply(db, number, f"AnnRakshak: {thanks}", problem.farm_id)
    db.commit()
    return {"matched": True, "followup_id": fu.id, "response": answer, "escalated": "case" in out}


@router.post("/inbound")
async def inbound(request: Request, db: Session = Depends(get_db), kb: KB = Depends(get_kb)):
    return await _inbound(request, db, kb, None)


@router.post("/inbound/{secret}")
async def inbound_with_secret(secret: str, request: Request, db: Session = Depends(get_db),
                              kb: KB = Depends(get_kb)):
    """For a provider whose callback cannot carry a header (MSG91's cannot):
    the secret is the URL's last segment, redacted from the access log."""
    return await _inbound(request, db, kb, secret)


async def _inbound(request: Request, db: Session, kb: KB, in_path: str | None):
    limit(f"sms-in:ip:{client_ip(request)}", 300, 60)
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            raw = await request.json()
        except ValueError:
            raise HTTPException(400, "not JSON") from None
        params = {str(k): str(v) for k, v in (raw.items() if isinstance(raw, dict) else [])}
    else:
        params = {k: str(v) for k, v in (await request.form()).items()}
    if not _authentic(request, params, in_path):
        log.warning("sms inbound refused: no valid secret or signature")
        raise HTTPException(403, "not a recognised SMS provider")
    sender = next((params[f] for f in SENDER_FIELDS if params.get(f)), "")
    text = next((params[f] for f in TEXT_FIELDS if params.get(f)), "")
    number = auth.normalise_phone(sender)
    out = await run_in_threadpool(handle, db, kb, number, text[:500])
    log.info("sms inbound from %s: %s", sms.mask(number or sender), out.get("reason") or out.get("response"))
    if request.headers.get("x-twilio-signature"):
        # Twilio wants TwiML back; an empty response means "nothing more to send".
        return Response('<?xml version="1.0" encoding="UTF-8"?><Response/>', media_type="application/xml")
    return out
