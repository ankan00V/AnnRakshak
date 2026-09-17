"""Sign-in: one-time codes, sessions, roles and who may see which farm.

Two roles. A FARMER sees only their own farms (a demo farmer sees the seeded
demo farms). An EXPERT — KVK scientist, agriculture officer, agronomist — gets
the expert console and the officials' dashboard, and may open any farm a case
comes from. Both sign in with their mobile number or email.

One-time codes: 6 digits, kept only as a salted SHA-256, 5 minutes, 5 tries,
a 30-second wait between sends, rate limited per destination and per IP.
There is no free SMS gateway yet, so every code goes to the account's email
by SMTP, whichever identifier was typed.

Sessions: an opaque random token in an HttpOnly, SameSite=Lax cookie; only
its hash is stored, so a database leak does not leak sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response, WebSocket
from starlette.requests import HTTPConnection
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.kb import tr
from app.db import get_db
from app.models import Alert, Farm, FollowUp, OtpChallenge, Problem, User, UserSession

COOKIE = "ar_session"
PHONE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian mobile numbers
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


class AuthError(HTTPException):
    pass


# What a person sees when sign-in goes wrong, in their language. Other
# languages come from the translation memory (translate_i18n.py reads this).
MESSAGES = {
    "sign_in": {"en": "Please sign in.", "hi": "कृपया साइन इन करें।", "mr": "कृपया साइन इन करा."},
    "wrong_area": {"en": "This part of AnnRakshak is for {role}s.", "hi": "AnnRakshak का यह हिस्सा {role} के लिए है।",
                   "mr": "AnnRakshak चा हा भाग {role} साठी आहे."},
    "not_your_farm": {"en": "This farm belongs to someone else.", "hi": "यह खेत किसी और का है।",
                      "mr": "हे शेत दुसऱ्या कोणाचे आहे."},
    "otp_wait": {"en": "Please wait {s} seconds before asking for a new code.",
                 "hi": "नया कोड माँगने से पहले {s} सेकंड रुकें।", "mr": "नवीन कोड मागण्यापूर्वी {s} सेकंद थांबा."},
    "otp_invalid": {"en": "This code is not valid. Ask for a new code.", "hi": "यह कोड मान्य नहीं है। नया कोड माँगें।",
                    "mr": "हा कोड वैध नाही. नवीन कोड मागा."},
    "otp_used": {"en": "This code was already used. Ask for a new code.",
                 "hi": "यह कोड पहले ही इस्तेमाल हो चुका है। नया कोड माँगें।",
                 "mr": "हा कोड आधीच वापरला गेला आहे. नवीन कोड मागा."},
    "otp_expired": {"en": "The code has expired. Ask for a new code.", "hi": "कोड की समय-सीमा खत्म हो गई। नया कोड माँगें।",
                    "mr": "कोडची मुदत संपली. नवीन कोड मागा."},
    "otp_locked": {"en": "Too many wrong tries. Ask for a new code.", "hi": "बहुत बार गलत कोड डाला गया। नया कोड माँगें।",
                   "mr": "खूप वेळा चुकीचा कोड टाकला. नवीन कोड मागा."},
    "otp_wrong": {"en": "Wrong code. {left} tries left.", "hi": "गलत कोड। {left} कोशिश बाकी।",
                  "mr": "चुकीचा कोड. {left} प्रयत्न बाकी."},
}


def say(key: str, lang: str = "en", **kw) -> str:
    return tr(MESSAGES[key], lang).format(**kw)


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


# --------------------------------------------------------------------------
# Destinations
# --------------------------------------------------------------------------

def normalise_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return f"+91{digits}" if PHONE_RE.match(digits) else None


def normalise_email(raw: str) -> str | None:
    e = (raw or "").strip().lower()
    return e if EMAIL_RE.match(e) and len(e) <= 200 else None


def mask(channel: str, dest: str) -> str:
    if channel == "phone":
        return f"+91 ••••••{dest[-4:]}"
    name, _, domain = dest.partition("@")
    return f"{name[:2]}{'•' * max(1, len(name) - 2)}@{domain}"


# --------------------------------------------------------------------------
# One-time codes
# --------------------------------------------------------------------------

def _hash(salt: str, code: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


def issue_otp(db: Session, *, channel: str, dest: str, purpose: str, role: str,
              lang: str = "en") -> tuple[OtpChallenge, str]:
    last = db.scalar(select(OtpChallenge).where(OtpChallenge.destination == dest)
                     .order_by(OtpChallenge.id.desc()).limit(1))
    if last and (now() - last.created_at).total_seconds() < config.OTP_RESEND_SECONDS:
        wait = config.OTP_RESEND_SECONDS - int((now() - last.created_at).total_seconds())
        raise AuthError(429, say("otp_wait", lang, s=wait), headers={"Retry-After": str(wait)})
    code = f"{secrets.randbelow(10 ** config.OTP_DIGITS):0{config.OTP_DIGITS}d}"
    salt = secrets.token_hex(16)
    ch = OtpChallenge(public_id=secrets.token_urlsafe(18), channel=channel, destination=dest, purpose=purpose,
                      role=role, code_hash=_hash(salt, code), salt=salt, created_at=now(),
                      expires_at=now() + timedelta(minutes=config.OTP_TTL_MINUTES))
    db.add(ch)
    db.flush()
    return ch, code


def check_otp(db: Session, public_id: str, code: str, *, purpose: str, lang: str = "en") -> OtpChallenge:
    ch = db.scalar(select(OtpChallenge).where(OtpChallenge.public_id == public_id))
    if ch is None or ch.purpose != purpose:
        raise AuthError(400, say("otp_invalid", lang))
    if ch.consumed_at is not None:
        raise AuthError(400, say("otp_used", lang))
    if ch.expires_at < now():
        raise AuthError(400, say("otp_expired", lang))
    if ch.attempts >= config.OTP_MAX_ATTEMPTS:
        raise AuthError(429, say("otp_locked", lang))
    ch.attempts += 1
    ok = hmac.compare_digest(ch.code_hash, _hash(ch.salt, (code or "").strip()))
    if not ok:
        db.commit()  # the failed attempt counts even though we raise
        left = config.OTP_MAX_ATTEMPTS - ch.attempts
        raise AuthError(400, say("otp_wrong", lang, left=left) if left else say("otp_locked", lang))
    ch.consumed_at = now()
    return ch


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, user: User, response: Response, user_agent: str | None) -> None:
    token = secrets.token_urlsafe(32)
    db.add(UserSession(user_id=user.id, token_hash=_token_hash(token), created_at=now(),
                       expires_at=now() + timedelta(days=config.SESSION_DAYS), user_agent=(user_agent or "")[:200]))
    user.last_login_at = now()
    response.set_cookie(COOKIE, token, max_age=config.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=config.COOKIE_SECURE, path="/")


def end_session(db: Session, token: str | None, response: Response) -> None:
    if token:
        s = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
        if s and s.revoked_at is None:
            s.revoked_at = now()
    response.delete_cookie(COOKIE, path="/")


def user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = db.execute(select(UserSession, User).join(User, User.id == UserSession.user_id)
                     .where(UserSession.token_hash == _token_hash(token))).first()  # one round trip
    if row is None:
        return None
    s, user = row
    if s.revoked_at is not None or s.expires_at < now():
        return None
    if s.last_seen_at is None or (now() - s.last_seen_at) > timedelta(hours=1):
        s.last_seen_at = now()
        db.commit()
    return user


_UNSET = object()


def current_user(request: HTTPConnection, db: Session) -> User | None:
    """The signed-in user, looked up once per request (the router guard and the
    handler both ask)."""
    cached = getattr(request.state, "ar_user", _UNSET)
    if cached is _UNSET:
        cached = user_from_token(db, request.cookies.get(COOKIE))
        request.state.ar_user = cached
    return cached


def ws_user(ws: WebSocket, db: Session) -> User | None:
    return user_from_token(db, ws.cookies.get(COOKIE))


# --------------------------------------------------------------------------
# Who may see what
# --------------------------------------------------------------------------

def can_open_farm(user: User | None, farm: Farm) -> bool:
    if not config.AUTH_ENFORCE:
        return True
    if user is None:
        return False
    if user.role == "expert":
        return True  # experts open the farm a case comes from
    return farm.user_id == user.id or (user.is_demo and farm.is_demo)


def farm_ids_for(db: Session, user: User | None) -> list[int] | None:
    """Farms this user may list; None means all (auth off, or an expert)."""
    if not config.AUTH_ENFORCE or (user and user.role == "expert"):
        return None
    if user is None:
        return []
    q = select(Farm.id).where(Farm.user_id == user.id)
    if user.is_demo:
        q = select(Farm.id).where((Farm.user_id == user.id) | Farm.is_demo.is_(True))
    return list(db.scalars(q).all())


def _farm_of(db: Session, name: str, value: str) -> Farm | None:
    try:
        key = int(value)
    except ValueError:
        return None
    if name == "farm_id":
        return db.get(Farm, key)
    if name == "problem_id":
        p = db.get(Problem, key)
        return db.get(Farm, p.farm_id) if p else None
    if name == "alert_id":
        a = db.get(Alert, key)
        return db.get(Farm, a.farm_id) if a else None
    if name == "followup_id":
        f = db.get(FollowUp, key)
        p = db.get(Problem, f.problem_id) if f else None
        return db.get(Farm, p.farm_id) if p else None
    return None


def guard(request: HTTPConnection, db: Session, role: str | None = None) -> User | None:
    """Router-level check: the right role, and ownership of whatever farm the
    URL points at (directly or through a problem, alert or follow-up)."""
    if not config.AUTH_ENFORCE:
        return None
    user = current_user(request, db)
    if role is not None:
        if user is None:
            raise AuthError(401, say("sign_in"))
        if user.role != role:
            raise AuthError(403, say("wrong_area", role=role))
    for name in ("farm_id", "problem_id", "alert_id", "followup_id"):
        if name in request.path_params:
            if user is None:
                raise AuthError(401, say("sign_in"))
            farm = _farm_of(db, name, request.path_params[name])
            if farm is not None and not can_open_farm(user, farm):
                raise AuthError(403, say("not_your_farm"))
    return user


def require(role: str | None = None):
    """A router dependency: `APIRouter(dependencies=[Depends(auth.require("expert"))])`.
    WebSockets check for themselves (live.py), since an HTTP error cannot be
    sent on a socket that is not yet accepted."""

    def dep(conn: HTTPConnection, db: Session = Depends(get_db)) -> None:
        if conn.scope["type"] != "websocket":
            guard(conn, db, role)

    return dep


def require_user(conn: HTTPConnection, db: Session = Depends(get_db)) -> None:
    """A route dependency: anyone signed in (paid services such as voice)."""
    if config.AUTH_ENFORCE and current_user(conn, db) is None:
        raise AuthError(401, say("sign_in"))


def signed_in(request: Request, db: Session) -> User | None:
    """The caller, or 401 when sign-in is enforced and nobody is signed in."""
    user = current_user(request, db)
    if user is None and config.AUTH_ENFORCE:
        raise AuthError(401, say("sign_in"))
    return user


def check_farm(user: User | None, farm: Farm) -> None:
    if not can_open_farm(user, farm):
        raise AuthError(403, say("not_your_farm"))
