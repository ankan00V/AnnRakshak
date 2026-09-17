"""Sign-up, sign-in and sign-out for the two roles.

  GET  /api/auth/options          choices for the sign-up forms (districts, crops, designations ...)
  POST /api/auth/otp              email a one-time code (sign-up, or login by mobile number or email)
  POST /api/auth/signup/farmer    verify the code; create the farmer, their profile and first farm
  POST /api/auth/signup/expert    verify the code; create the expert and their profile
  POST /api/auth/login            verify the code; start a session
  POST /api/auth/demo             sign in as the demo farmer or demo expert (demo builds only)
  GET  /api/auth/me               who is signed in
  POST /api/auth/logout

The two sign-ups ask different things because the two people need different
things from the app. A farmer's answers set up the farm the whole advisory runs
on — where it is (weather, district prior, spread radius), the crop and sowing
date (crop stage), area, how it is watered, and Soil Health Card pH. An expert's
answers decide which cases reach them and whether their verdicts can be trusted
— designation, organisation, employee ID, qualification, experience, the
districts and crops they cover, their specialities and the languages they can
answer farmers in.

Both give a mobile number and an email. There is no free SMS gateway yet, so
every code goes to the email (config.OTP_CHANNEL).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, config, geo, mailer, services
from app.db import get_db
from app.i18n import LANGS
from app.kb import KB, get_kb, tr
from app.limits import client_ip, limit
from app.models import ExpertProfile, Farm, FarmerProfile, User

router = APIRouter(prefix="/api/auth", tags=["auth"])

Role = Literal["farmer", "expert"]
Irrigation = Literal["rainfed", "canal", "borewell", "open_well", "farm_pond", "drip", "sprinkler"]
DESIGNATIONS = {
    "kvk_scientist": "KVK scientist / Subject Matter Specialist",
    "agri_officer": "Agriculture officer (Taluka / District / Circle)",
    "agri_assistant": "Agriculture assistant (Krishi Sahayak)",
    "university": "Agricultural university scientist",
    "icar": "ICAR institute scientist",
    "private_agronomist": "Private agronomist / FPO advisor",
}
QUALIFICATIONS = {"diploma": "Diploma in agriculture", "bsc_agri": "B.Sc. (Agri) or equivalent",
                  "msc_agri": "M.Sc. (Agri)", "phd": "Ph.D.", "other": "Other"}
SPECIALITIES = {"plant_pathology": "Plant pathology (diseases)", "entomology": "Entomology (pests)",
                "agronomy": "Agronomy", "soil_science": "Soil science", "extension": "Extension",
                "weed_science": "Weed science"}
MESSAGES = {
    "bad_email": {"en": "Enter a valid email address.", "hi": "सही ईमेल पता डालें।", "mr": "योग्य ईमेल पत्ता टाका."},
    "bad_phone": {"en": "Enter a 10-digit Indian mobile number.", "hi": "10 अंकों का भारतीय मोबाइल नंबर डालें।",
                  "mr": "10 अंकी भारतीय मोबाइल नंबर टाका."},
    "email_taken": {"en": "This email is already registered. Please log in.",
                    "hi": "यह ईमेल पहले से पंजीकृत है। कृपया लॉग इन करें।",
                    "mr": "हा ईमेल आधीच नोंदणीकृत आहे. कृपया लॉग इन करा."},
    "phone_taken": {"en": "This mobile number is already registered. Please log in.",
                    "hi": "यह मोबाइल नंबर पहले से पंजीकृत है। कृपया लॉग इन करें।",
                    "mr": "हा मोबाइल नंबर आधीच नोंदणीकृत आहे. कृपया लॉग इन करा."},
    "no_account": {"en": "No account with this mobile number or email yet. Please sign up.",
                   "hi": "इस मोबाइल नंबर या ईमेल से कोई खाता नहीं है। कृपया साइन अप करें।",
                   "mr": "या मोबाइल नंबर किंवा ईमेलने कोणतेही खाते नाही. कृपया साइन अप करा."},
    "is_farmer": {"en": "This account is registered as a farmer. Choose Farmer above.",
                  "hi": "यह खाता किसान के रूप में पंजीकृत है। ऊपर किसान चुनें।",
                  "mr": "हे खाते शेतकरी म्हणून नोंदणीकृत आहे. वर शेतकरी निवडा."},
    "is_expert": {"en": "This account is registered as an expert. Choose Expert / Officer above.",
                  "hi": "यह खाता विशेषज्ञ के रूप में पंजीकृत है। ऊपर विशेषज्ञ / अधिकारी चुनें।",
                  "mr": "हे खाते तज्ज्ञ म्हणून नोंदणीकृत आहे. वर तज्ज्ञ / अधिकारी निवडा."},
    "no_email": {"en": "This account has no email to send the code to. Call the Kisan Call Centre, 1800-180-1551.",
                 "hi": "इस खाते में कोड भेजने के लिए ईमेल नहीं है। किसान कॉल सेंटर 1800-180-1551 पर फ़ोन करें।",
                 "mr": "या खात्यात कोड पाठवण्यासाठी ईमेल नाही. किसान कॉल सेंटर 1800-180-1551 वर फोन करा."},
    "mail_failed": {"en": "We could not send the email just now. Please try again.",
                    "hi": "अभी ईमेल नहीं भेज पाए। कृपया फिर से कोशिश करें।",
                    "mr": "आत्ता ईमेल पाठवता आला नाही. कृपया पुन्हा प्रयत्न करा."},
    "other_code": {"en": "This code was for a different kind of account. Ask for a new code.",
                   "hi": "यह कोड किसी दूसरे प्रकार के खाते के लिए था। नया कोड माँगें।",
                   "mr": "हा कोड दुसऱ्या प्रकारच्या खात्यासाठी होता. नवीन कोड मागा."},
    "consent": {"en": "Please agree to how your data is used.", "hi": "कृपया डेटा के उपयोग से सहमति दें।",
                "mr": "कृपया माहितीच्या वापराला संमती द्या."},
    "pick_lists": {"en": "Please choose from the lists: {items}", "hi": "कृपया सूची में से चुनें: {items}",
                   "mr": "कृपया यादीतून निवडा: {items}"},
    "no_place": {"en": "We could not find that place. Allow location while you are in the field, or check the "
                       "district and village spelling.",
                 "hi": "यह जगह नहीं मिली। खेत में रहते हुए स्थान की अनुमति दें, या ज़िला और गाँव की वर्तनी जाँचें।",
                 "mr": "ही जागा सापडली नाही. शेतात असताना स्थानाची परवानगी द्या, किंवा जिल्हा व गावाचे स्पेलिंग तपासा."},
}
LANG_NAMES = {"en": "English", "hi": "हिन्दी", "mr": "मराठी", "bn": "বাংলা", "ta": "தமிழ்", "te": "తెలుగు",
              "kn": "ಕನ್ನಡ", "ml": "മലയാളം", "gu": "ગુજરાતી", "pa": "ਪੰਜਾਬੀ", "od": "ଓଡ଼ିଆ"}


def _say(key: str, lang: str, **kw) -> str:
    return tr(MESSAGES[key], lang if lang in LANGS else "en").format(**kw)


def _districts() -> list[str]:
    return sorted(services.rainfall_normals()["district_to_subdivision"])


@router.get("/options")
def options(lang: str = "en", kb: KB = Depends(get_kb)):
    return {
        "districts": _districts(),
        "crops": [{"id": c, "name": tr(v["names"], lang)} for c, v in kb.crops.items()],
        "languages": [{"code": c, "name": LANG_NAMES[c]} for c in LANGS],
        "irrigation": list(Irrigation.__args__),
        "designations": [{"id": k, "name": v} for k, v in DESIGNATIONS.items()],
        "qualifications": [{"id": k, "name": v} for k, v in QUALIFICATIONS.items()],
        "specialities": [{"id": k, "name": v} for k, v in SPECIALITIES.items()],
        "otp": {"digits": config.OTP_DIGITS, "minutes": config.OTP_TTL_MINUTES, "channel": config.OTP_CHANNEL},
        "demo_login": config.DEMO_LOGIN,
    }


# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------

def _email(raw: str | None, lang: str) -> str:
    e = auth.normalise_email(raw or "")
    if e is None:
        raise HTTPException(422, _say("bad_email", lang))
    return e


def _phone(raw: str | None, lang: str) -> str:
    p = auth.normalise_phone(raw or "")
    if p is None:
        raise HTTPException(422, _say("bad_phone", lang))
    return p


def _by(db: Session, col, value: str) -> User | None:
    return db.scalar(select(User).where(col == value))


def _lookup(db: Session, identifier: str, lang: str) -> User | None:
    """A login identifier: a mobile number or an email."""
    if "@" in identifier:
        return _by(db, User.email, _email(identifier, lang))
    return _by(db, User.phone, _phone(identifier, lang))


def _unused(db: Session, email: str, phone: str, lang: str) -> None:
    if _by(db, User.email, email):
        raise HTTPException(409, _say("email_taken", lang))
    if _by(db, User.phone, phone):
        raise HTTPException(409, _say("phone_taken", lang))


# --------------------------------------------------------------------------
# One-time codes — emailed for now (config.OTP_CHANNEL)
# --------------------------------------------------------------------------

class OtpIn(BaseModel):
    role: Role
    purpose: Literal["signup", "login"]
    email: str | None = Field(default=None, max_length=200)
    """Sign-up: where the code goes."""
    phone: str | None = Field(default=None, max_length=20)
    """Sign-up: checked for an existing account now, saved at sign-up."""
    identifier: str | None = Field(default=None, max_length=200)
    """Login: the mobile number or email on the account."""
    lang: str = "en"


@router.post("/otp")
def request_otp(body: OtpIn, request: Request, db: Session = Depends(get_db)):
    limit(f"otp:ip:{client_ip(request)}", 20, 900)
    lang = body.lang if body.lang in LANGS else "en"
    if body.purpose == "signup":
        email = _email(body.email, lang)
        _unused(db, email, _phone(body.phone, lang), lang)
    else:
        user = _lookup(db, body.identifier or "", lang)
        if user is None:
            raise HTTPException(404, _say("no_account", lang))
        if user.role != body.role:
            raise HTTPException(409, _say(f"is_{user.role}", lang))
        if not user.email:
            raise HTTPException(409, _say("no_email", lang))
        email = user.email
    limit(f"otp:dest:{email}", 5, 900)
    ch, code = auth.issue_otp(db, channel=config.OTP_CHANNEL, dest=email, purpose=body.purpose, role=body.role,
                              lang=lang)
    subject, text, html = mailer.otp_message(code, body.purpose, config.OTP_TTL_MINUTES, lang)
    status, _err = mailer.send(email, subject, text, html)
    if status == "failed":
        db.rollback()
        raise HTTPException(502, _say("mail_failed", lang))
    db.commit()
    return {"challenge_id": ch.public_id, "channel": config.OTP_CHANNEL, "sent_to": auth.mask("email", email),
            "expires_in": config.OTP_TTL_MINUTES * 60, "resend_in": config.OTP_RESEND_SECONDS,
            "digits": config.OTP_DIGITS}


def _verified(db: Session, body, purpose: str, role: str):
    lang = body.lang if body.lang in LANGS else "en"
    ch = auth.check_otp(db, body.challenge_id, body.code, purpose=purpose, lang=lang)
    if ch.role != role:
        raise HTTPException(400, _say("other_code", lang))
    return ch


# --------------------------------------------------------------------------
# Sign-up
# --------------------------------------------------------------------------

class FirstFarm(BaseModel):
    crop: str
    variety: str | None = Field(default=None, max_length=80)
    sowing_date: date
    area_acres: float = Field(gt=0, le=1000)
    irrigation: Irrigation
    soil_ph: float | None = Field(default=None, ge=3, le=11)
    """From the Soil Health Card, if the farmer has one."""


class FarmerSignup(BaseModel):
    challenge_id: str
    code: str = Field(min_length=4, max_length=8)
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(max_length=20)
    lang: str = "mr"
    state: str | None = Field(default=None, max_length=60)
    district: str = Field(min_length=2, max_length=60)
    """Any district in India (the Government's LGD list, or one typed in)."""
    taluka: str | None = Field(default=None, max_length=80)
    village: str = Field(min_length=2, max_length=80)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    """The phone's GPS at the field. Left out when the farmer refused location:
    the server then looks the place up, because everything the app says is read
    at a point."""
    location_from_gps: bool = False
    """True when the farmer allowed location while standing in the field. The
    app keeps asking until it is, because the weather, the spray window and the
    outbreak radius are all read at this spot."""
    total_land_acres: float | None = Field(default=None, gt=0, le=10000)
    farms: list[FirstFarm] = Field(min_length=1, max_length=6)
    """A farmer usually sows more than one crop — rice on one plot, cotton on
    another. Each is its own field, with its own stage, risks and advice."""
    consent: bool


class ExpertSignup(BaseModel):
    challenge_id: str
    code: str = Field(min_length=4, max_length=8)
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(max_length=20)
    designation: str
    organisation: str = Field(min_length=2, max_length=160)
    employee_id: str = Field(min_length=2, max_length=60)
    qualification: str
    experience_years: int = Field(ge=0, le=60)
    districts: list[str] = Field(min_length=1, max_length=40)
    crops: list[str] = Field(min_length=1)
    specialities: list[str] = Field(min_length=1)
    languages: list[str] = Field(min_length=1)
    lang: str = "en"


def _me(db: Session, user: User) -> dict:
    out = {"id": user.id, "role": user.role, "name": user.name, "phone": user.phone, "email": user.email,
           "lang": user.lang, "is_demo": user.is_demo}
    if user.role == "farmer":
        p = db.get(FarmerProfile, user.id)
        out["profile"] = {"state": p.state, "district": p.district, "taluka": p.taluka, "village": p.village,
                          "total_land_acres": p.total_land_acres} if p else None
        out["farm_ids"] = sorted(auth.farm_ids_for(db, user) or [])
    else:
        p = db.get(ExpertProfile, user.id)
        out["profile"] = {"designation": p.designation, "designation_name": DESIGNATIONS.get(p.designation),
                          "organisation": p.organisation, "districts": p.districts, "crops": p.crops,
                          "specialities": p.specialities, "languages": p.languages, "verified": p.verified,
                          "experience_years": p.experience_years} if p else None
    return out


@router.post("/signup/farmer", status_code=201)
def signup_farmer(body: FarmerSignup, request: Request, response: Response, db: Session = Depends(get_db),
                  kb: KB = Depends(get_kb)):
    if body.lang not in LANGS:
        raise HTTPException(422, "unknown language")
    if not body.consent:
        raise HTTPException(422, _say("consent", body.lang))
    bad = [f.crop for f in body.farms if f.crop not in kb.crops]
    if bad:
        raise HTTPException(422, _say("pick_lists", body.lang, items=", ".join(bad)))
    state, district = geo.match_district(body.state, body.district)
    lat, lon = body.lat, body.lon
    if lat is None or lon is None:  # location refused: look the place up instead
        at = geo.locate(state, district, body.village)
        if at is None:
            raise HTTPException(422, _say("no_place", body.lang))
        lat, lon = at["lat"], at["lon"]
    phone = _phone(body.phone, body.lang)
    ch = _verified(db, body, "signup", "farmer")
    _unused(db, ch.destination, phone, body.lang)
    name, village, taluka = body.name.strip(), body.village.strip(), (body.taluka or "").strip() or None
    user = User(role="farmer", name=name, phone=phone, email=ch.destination, lang=body.lang)
    db.add(user)
    db.flush()
    db.add(FarmerProfile(user_id=user.id, state=state, district=district, taluka=taluka, village=village,
                         total_land_acres=body.total_land_acres, consent_at=auth.now()))
    for f in body.farms:  # one row per plot: each has its own crop stage, risks and advice
        db.add(Farm(user_id=user.id, farmer_name=name, phone=phone, email=ch.destination, lang=body.lang,
                    crop=f.crop, variety=(f.variety or "").strip() or None, sowing_date=f.sowing_date,
                    state=state, district=district, taluka=taluka, village=village, lat=lat, lon=lon,
                    area_acres=f.area_acres, irrigation=f.irrigation, soil_ph=f.soil_ph,
                    location_source="gps" if body.location_from_gps else "district",
                    soil_ph_on=date.today() if f.soil_ph is not None else None))
    auth.start_session(db, user, response, request.headers.get("user-agent"))
    db.commit()
    return _me(db, user)


@router.post("/signup/expert", status_code=201)
def signup_expert(body: ExpertSignup, request: Request, response: Response, db: Session = Depends(get_db),
                  kb: KB = Depends(get_kb)):
    lang = body.lang if body.lang in LANGS else "en"
    districts = set(_districts())
    bad = [x for x, allowed in ((body.designation, DESIGNATIONS), (body.qualification, QUALIFICATIONS)) if x not in allowed] \
        + [d for d in body.districts if d not in districts] + [c for c in body.crops if c not in kb.crops] \
        + [s for s in body.specialities if s not in SPECIALITIES] + [x for x in body.languages if x not in LANGS]
    if bad:
        raise HTTPException(422, _say("pick_lists", lang, items=", ".join(bad[:5])))
    phone = _phone(body.phone, lang)
    ch = _verified(db, body, "signup", "expert")
    _unused(db, ch.destination, phone, lang)
    user = User(role="expert", name=body.name.strip(), email=ch.destination, phone=phone,
                lang=body.lang if body.lang in LANGS else "en")
    db.add(user)
    db.flush()
    db.add(ExpertProfile(user_id=user.id, designation=body.designation, organisation=body.organisation.strip(),
                         employee_id=body.employee_id.strip(), qualification=body.qualification,
                         experience_years=body.experience_years, districts=sorted(set(body.districts)),
                         crops=sorted(set(body.crops)), specialities=sorted(set(body.specialities)),
                         languages=sorted(set(body.languages)), verified=config.EXPERT_AUTO_VERIFY))
    auth.start_session(db, user, response, request.headers.get("user-agent"))
    db.commit()
    return _me(db, user)


# --------------------------------------------------------------------------
# Login, demo, me, logout
# --------------------------------------------------------------------------

class LoginIn(BaseModel):
    challenge_id: str
    code: str = Field(min_length=4, max_length=8)
    role: Role
    lang: str = "en"


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ch = _verified(db, body, "login", body.role)
    user = _by(db, User.email, ch.destination)
    if user is None or user.role != ch.role:
        raise HTTPException(404, _say("no_account", body.lang))
    auth.start_session(db, user, response, request.headers.get("user-agent"))
    db.commit()
    return _me(db, user)


class DemoIn(BaseModel):
    role: Role


@router.post("/demo")
def demo(body: DemoIn, request: Request, response: Response, db: Session = Depends(get_db),
         kb: KB = Depends(get_kb)):
    """One tap into the seeded demo farms, or the expert console as a demo KVK
    scientist — for judges and field demos. Off when ANNRAKSHAK_DEMO_LOGIN=off."""
    if not config.DEMO_LOGIN:
        raise HTTPException(404, "demo sign-in is off")
    email = f"demo-{body.role}@annrakshak.local"
    user = _by(db, User.email, email)
    if user is None:
        user = User(role=body.role, name="Demo farmer" if body.role == "farmer" else "Demo expert",
                    email=email, lang="mr" if body.role == "farmer" else "en", is_demo=True)
        db.add(user)
        db.flush()
        if body.role == "farmer":
            db.add(FarmerProfile(user_id=user.id, district="Bhandara", village="Demo", consent_at=auth.now()))
        else:
            db.add(ExpertProfile(user_id=user.id, designation="kvk_scientist", organisation="Demo KVK",
                                 employee_id="DEMO", qualification="msc_agri", experience_years=10,
                                 districts=_districts(), crops=list(kb.crops), specialities=list(SPECIALITIES),
                                 languages=["en", "hi", "mr"], verified=True))
    auth.start_session(db, user, response, request.headers.get("user-agent"))
    db.commit()
    return _me(db, user)


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    user = auth.current_user(request, db)
    if user is None:
        raise HTTPException(401, "not signed in")
    return _me(db, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth.end_session(db, request.cookies.get(auth.COOKIE), response)
    db.commit()
    return {"signed_out": True}
