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

import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, config, erasure, geo, mailer, services, turnstile
from app.db import SUPERVISOR_DESIGNATIONS, get_db
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
DEPARTMENTS = {
    "state_agri": "State Department of Agriculture",
    "kvk": "Krishi Vigyan Kendra (ICAR)",
    "icar": "ICAR institute",
    "sau": "State Agricultural University",
    "atma": "ATMA / extension project",
    "other": "Other (FPO, NGO, private advisory)",
}
"""Which service an officer belongs to. A district office verifying a stranger
asks this first, because where somebody works decides who can vouch for them."""

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
    "declaration": {"en": "Please confirm the undertaking before continuing.",
                    "hi": "जारी रखने से पहले कृपया घोषणा की पुष्टि करें।",
                    "mr": "पुढे जाण्यापूर्वी कृपया घोषणेची खात्री करा."},
    "not_a_person": {"en": "Please complete the check above and try again.",
                     "hi": "कृपया ऊपर दी गई जाँच पूरी करें और फिर कोशिश करें।",
                     "mr": "कृपया वरील तपासणी पूर्ण करा आणि पुन्हा प्रयत्न करा."},
    "consent": {"en": "Please agree to how your data is used.", "hi": "कृपया डेटा के उपयोग से सहमति दें।",
                "mr": "कृपया माहितीच्या वापराला संमती द्या."},
    "districts_are_granted": {
        "en": "The district office adds a district to an officer's patch: {items}. You can drop one here.",
        "hi": "किसी अधिकारी के क्षेत्र में ज़िला जोड़ना ज़िला कार्यालय का काम है: {items}। यहाँ आप ज़िला हटा सकते हैं।",
        "mr": "अधिकाऱ्याच्या कार्यक्षेत्रात जिल्हा जोडणे हे जिल्हा कार्यालयाचे काम आहे: {items}. इथे तुम्ही जिल्हा काढू शकता.",
    },
    "pick_lists": {"en": "Please choose from the lists: {items}", "hi": "कृपया सूची में से चुनें: {items}",
                   "mr": "कृपया यादीतून निवडा: {items}"},
    "no_place": {"en": "We could not find that place. Allow location while you are in the field, or check the "
                       "district and village spelling.",
                 "hi": "यह जगह नहीं मिली। खेत में रहते हुए स्थान की अनुमति दें, या ज़िला और गाँव की वर्तनी जाँचें।",
                 "mr": "ही जागा सापडली नाही. शेतात असताना स्थानाची परवानगी द्या, किंवा जिल्हा व गावाचे स्पेलिंग तपासा."},
}
LANG_NAMES = {"en": "English", "hi": "हिन्दी", "mr": "मराठी", "bn": "বাংলা", "ta": "தமிழ்", "te": "తెలుగు",
              "kn": "ಕನ್ನಡ", "ml": "മലയാളം", "gu": "ગુજરાતી", "pa": "ਪੰਜਾਬੀ"}


def _say(key: str, lang: str, **kw) -> str:
    return tr(MESSAGES[key], lang if lang in LANGS else "en").format(**kw)


def _districts() -> list[str]:
    return sorted(services.rainfall_normals()["district_to_subdivision"])


def _official_districts() -> set[str]:
    """Every district the Government publishes — which is the list the sign-up
    form itself offers, from the same file.

    An officer's districts used to be checked against `_districts()` above:
    that is the IMD rainfall map, 36 Maharashtra districts, and it is the right
    list for reading a monsoon normal and the wrong one for saying where a
    person works. So an officer at KVK Kapurthala picked Hoshiarpur and
    Kapurthala out of the form's own list and was told to choose from the list
    — with no way forward, because the form was already right.
    """
    return {d["name"] for v in geo.places().values() for d in v["districts"]}


@router.get("/options")
def options(lang: str = "en", kb: KB = Depends(get_kb)):
    return {
        "districts": _districts(),
        "crops": [{"id": c, "name": tr(v["names"], lang)} for c, v in kb.crops.items()],
        "languages": [{"code": c, "name": LANG_NAMES[c]} for c in LANGS],
        "irrigation": list(Irrigation.__args__),
        "designations": [{"id": k, "name": v} for k, v in DESIGNATIONS.items()],
        "departments": [{"id": k, "name": v} for k, v in DEPARTMENTS.items()],
        "qualifications": [{"id": k, "name": v} for k, v in QUALIFICATIONS.items()],
        "specialities": [{"id": k, "name": v} for k, v in SPECIALITIES.items()],
        "otp": {"digits": config.OTP_DIGITS, "minutes": config.OTP_TTL_MINUTES, "channel": config.OTP_CHANNEL},
        "demo_login": config.DEMO_LOGIN,
        # The widget's public half. Absent means no box is shown at all.
        "turnstile_sitekey": config.TURNSTILE_SITEKEY if turnstile.configured() else None,
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


def _taken(db: Session, email: str, phone: str) -> str | None:
    """Which identifier is already on an account, if either is."""
    if _by(db, User.email, email):
        return "email"
    if _by(db, User.phone, phone):
        return "phone"
    return None


def _unused(db: Session, email: str, phone: str, lang: str) -> None:
    """The last word on a duplicate, held at the moment the account is made.

    The sign-up form asks /check first so it can object on the step that owns
    the field, but two sign-ups can still race between that answer and this
    one, so the guard stays here as well. The detail names the field, because
    an identifier typed on the first step is otherwise reported four steps
    later with nothing to point at.
    """
    field = _taken(db, email, phone)
    if field:
        raise HTTPException(409, {"message": _say(f"{field}_taken", lang), "field": field})


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
    turnstile_token: str | None = Field(default=None, max_length=2048)
    """What the Cloudflare widget hands back. Checked here because this is the
    call that spends money and reaches a real inbox."""
    lang: str = "en"


class CheckIn(BaseModel):
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    lang: str = "en"


@router.post("/check")
def check_identifiers(body: CheckIn, request: Request, db: Session = Depends(get_db)):
    """Is this email or mobile number free? Asked as a sign-up leaves the step
    that collects them.

    Before this, the only check ran inside /otp, on the last step: a number
    typed on step one came back rejected on step four, naming a field that was
    no longer on screen. It tells no one anything that asking for a code does
    not already tell them.
    """
    limit(f"check:ip:{client_ip(request)}", 40, 900)
    lang = body.lang if body.lang in LANGS else "en"
    field = _taken(db, _email(body.email, lang), _phone(body.phone, lang))
    return {"free": field is None, "field": field,
            "message": _say(f"{field}_taken", lang) if field else None}


@router.post("/otp")
def request_otp(body: OtpIn, request: Request, db: Session = Depends(get_db)):
    limit(f"otp:ip:{client_ip(request)}", 20, 900)
    lang = body.lang if body.lang in LANGS else "en"
    # Both sign-up and login start here, so one check covers both screens.
    passed, why = turnstile.verify(body.turnstile_token, client_ip(request))
    if not passed:
        raise HTTPException(403, _say("not_a_person", lang))
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
    date_basis: Literal["sown", "transplanted"] = "sown"
    """What sowing_date means. Rice is transplanted about three weeks after the
    nursery is sown, so a rice farm must say which date this is; for every other
    crop here there is only one date and it is the sowing."""
    area_acres: float = Field(gt=0, le=1000)
    irrigation: Irrigation
    soil_ph: float | None = Field(default=None, ge=3, le=11)
    """From the Soil Health Card, if the farmer has one."""


class FarmerSignup(BaseModel):
    challenge_id: str
    code: str = Field(min_length=4, max_length=8)
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(max_length=20)
    lang: str = "en"
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
    """What an officer gives before they may read a farmer's case.

    It is more than a farmer is asked for, deliberately. A farmer is asked the
    least that lets the app help them; an officer is asking for access to other
    people's fields, photographs and phone numbers, and a district office has
    to be able to check who they are before granting it. Everything here is
    something a state department or KVK portal already asks."""

    challenge_id: str
    code: str = Field(min_length=4, max_length=8)
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(max_length=20)

    # The post
    designation: str
    department: str
    organisation: str = Field(min_length=2, max_length=160)
    employee_id: str = Field(min_length=2, max_length=60)
    joined_service_on: date | None = None
    posted_since: date | None = None

    # The office, so there is somewhere to write to and somewhere to ring
    office_address: str = Field(min_length=4, max_length=240)
    block: str | None = Field(default=None, max_length=80)
    state: str = Field(min_length=2, max_length=60)
    pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    office_phone: str | None = Field(default=None, max_length=20)

    # Who can vouch for them. This is what verification actually rests on.
    reporting_name: str = Field(min_length=2, max_length=120)
    reporting_designation: str = Field(min_length=2, max_length=60)
    reporting_contact: str = Field(min_length=5, max_length=120)

    qualification: str
    experience_years: int = Field(ge=0, le=60)
    districts: list[str] = Field(min_length=1, max_length=40)
    crops: list[str] = Field(min_length=1)
    specialities: list[str] = Field(min_length=1)
    languages: list[str] = Field(min_length=1)
    declaration: bool
    """They put their name to it: the details are true, and farmers' data is
    handled under their office's rules."""
    lang: str = "en"


def _designation_name(designation: str | None) -> str | None:
    """The post as a person reads it. A designation saved before the list was
    settled is titled rather than left blank, so an older profile still names
    its holder's post instead of showing a gap."""
    if not designation:
        return None
    return DESIGNATIONS.get(designation) or designation.replace("_", " ").capitalize()


def _me(db: Session, user: User) -> dict:
    out = {"id": user.id, "role": user.role, "name": user.name, "phone": user.phone, "email": user.email,
           "lang": user.lang, "is_demo": user.is_demo,
           "created_at": user.created_at.isoformat() if user.created_at else None}
    if user.role == "farmer":
        p = db.get(FarmerProfile, user.id)
        out["profile"] = {"state": p.state, "district": p.district, "taluka": p.taluka, "village": p.village,
                          "total_land_acres": p.total_land_acres} if p else None
        out["farm_ids"] = sorted(auth.farm_ids_for(db, user) or [])
    else:
        p = db.get(ExpertProfile, user.id)
        # `supervisor` travels with the profile so a screen can show the actions
        # this desk may actually take. Without it the console offered every
        # officer the supervisor-only buttons and let the server refuse them.
        out["profile"] = {"designation": p.designation, "designation_name": _designation_name(p.designation),
                          "organisation": p.organisation, "districts": p.districts,
                          # The states those districts sit in. The console says
                          # where it is watching, and it used to say Maharashtra
                          # to an officer in Punjab.
                          "states": geo.states_of(p.districts), "crops": p.crops,
                          "specialities": p.specialities, "languages": p.languages, "verified": p.verified,
                          "supervisor": p.supervisor, "experience_years": p.experience_years,
                          "employee_id": p.employee_id, "qualification": p.qualification,
                          "department": p.department, "office_address": p.office_address,
                          "block": p.block, "state": p.state, "pincode": p.pincode,
                          "office_phone": p.office_phone,
                          "joined_service_on": p.joined_service_on.isoformat() if p.joined_service_on else None,
                          "posted_since": p.posted_since.isoformat() if p.posted_since else None,
                          "reporting_name": p.reporting_name,
                          "reporting_designation": p.reporting_designation,
                          "reporting_contact": p.reporting_contact} if p else None
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
                    date_basis=f.date_basis,
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
    districts = _official_districts()
    if not body.declaration:
        raise HTTPException(422, _say("declaration", lang))
    bad = [x for x, allowed in ((body.designation, DESIGNATIONS), (body.department, DEPARTMENTS),
                                (body.qualification, QUALIFICATIONS)) if x not in allowed] \
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
    state, _ = geo.match_district(body.state, body.districts[0])
    db.add(ExpertProfile(user_id=user.id, designation=body.designation, organisation=body.organisation.strip(),
                         employee_id=body.employee_id.strip(), qualification=body.qualification,
                         experience_years=body.experience_years, districts=sorted(set(body.districts)),
                         crops=sorted(set(body.crops)), specialities=sorted(set(body.specialities)),
                         languages=sorted(set(body.languages)), verified=config.EXPERT_AUTO_VERIFY,
                         # The office, so a district has somewhere to write and
                         # somewhere to ring, and the person who can vouch for
                         # them — which is what verification actually rests on.
                         department=body.department, office_address=body.office_address.strip(),
                         block=(body.block or "").strip() or None, state=state or body.state.strip(),
                         pincode=body.pincode, office_phone=(body.office_phone or "").strip() or None,
                         joined_service_on=body.joined_service_on, posted_since=body.posted_since,
                         reporting_name=body.reporting_name.strip(),
                         reporting_designation=body.reporting_designation.strip(),
                         reporting_contact=body.reporting_contact.strip(),
                         declared_at=auth.now(),
                         # The rank follows the post. Without this every sign-up
                         # was an ordinary desk, so a district whose officers had
                         # all signed up had nobody who could route its backlog
                         # or verify the next arrival.
                         supervisor=body.designation in SUPERVISOR_DESIGNATIONS))
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


DEMO_OFFICE = {
    "department": "kvk",
    "office_address": "Krishi Vigyan Kendra, Sakoli Road",
    "block": "Sakoli",
    "state": "Maharashtra",
    "pincode": "441802",
    "office_phone": "07184255033",
    "joined_service_on": date(2016, 7, 1),
    "posted_since": date(2022, 4, 1),
    "reporting_name": "Smt. A. Deshmukh",
    "reporting_designation": "District Agriculture Officer",
    "reporting_contact": "dao.bhandara@example.gov.in",
}
"""The rest of a district officer's record, for the demo account. Sign-up asks
all of this now and the officer's own record screen shows it, so a demo that
answers none of it is a page of blanks in front of a judge."""


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
                    email=email, lang="en", is_demo=True)
        db.add(user)
        db.flush()
        if body.role == "farmer":
            db.add(FarmerProfile(user_id=user.id, district="Bhandara", village="Demo", consent_at=auth.now()))
        else:
            db.add(ExpertProfile(user_id=user.id, designation="kvk_scientist", organisation="Demo KVK",
                                 employee_id="DEMO", qualification="msc_agri", experience_years=10,
                                 districts=_districts(), crops=list(kb.crops), specialities=list(SPECIALITIES),
                                 languages=["en", "hi", "mr"], verified=True, supervisor=True,
                                 **DEMO_OFFICE))
    elif user.role == "expert":
        # The demo account was made before sign-up asked where an officer sits
        # and who vouches for them, so its own record screen showed half a
        # page of blanks to whoever opened it. Fill what is still empty,
        # without touching anything a demo session has changed.
        p = db.get(ExpertProfile, user.id)
        for field, value in DEMO_OFFICE.items():
            if p is not None and getattr(p, field, None) is None:
                setattr(p, field, value)
    auth.start_session(db, user, response, request.headers.get("user-agent"))
    db.commit()
    return _me(db, user)


class ProfileIn(BaseModel):
    """What a person may change about themselves.

    Not everything on the record: an officer cannot verify themselves, promote
    themselves to supervisor, or rewrite the employee ID and the department the
    district office checked them against. Those are the office's to change, and
    a profile screen that offered them would be offering a way around
    verification."""

    # Either role. The phone and the email are deliberately absent: they are
    # what a sign-in code is sent to, so changing one proves nothing unless a
    # code proves it, and that belongs to the sign-in screen.
    name: str | None = Field(default=None, min_length=2, max_length=120)
    lang: str | None = None

    # A farmer: where they are, and how much land they work
    state: str | None = Field(default=None, max_length=60)
    district: str | None = Field(default=None, max_length=60)
    taluka: str | None = Field(default=None, max_length=80)
    village: str | None = Field(default=None, max_length=80)
    total_land_acres: float | None = Field(default=None, ge=0, le=100000)

    # An officer: their post's reach and the office they sit in
    organisation: str | None = Field(default=None, min_length=2, max_length=160)
    experience_years: int | None = Field(default=None, ge=0, le=60)
    districts: list[str] | None = None
    crops: list[str] | None = None
    specialities: list[str] | None = None
    languages: list[str] | None = None
    office_address: str | None = Field(default=None, max_length=240)
    block: str | None = Field(default=None, max_length=80)
    pincode: str | None = Field(default=None, max_length=6)
    office_phone: str | None = Field(default=None, max_length=20)
    # The reporting line is absent on purpose: it is the evidence the district
    # office verified this person against, and a record you can rewrite is not
    # evidence of anything.


@router.patch("/me/profile")
def update_profile(body: ProfileIn, request: Request, db: Session = Depends(get_db),
                   kb: KB = Depends(get_kb)):
    """Change your own details — the same record for both roles, one door.

    Only the fields actually sent are touched, so a screen may save one line
    without having to send the whole profile back."""
    limit(f"profile:{client_ip(request)}", max_hits=30, window_s=60)
    user = auth.current_user(request, db)
    if user is None:
        raise HTTPException(401, "not signed in")
    sent = body.model_dump(exclude_unset=True)

    if "name" in sent and sent["name"]:
        user.name = sent["name"].strip()
    if sent.get("lang"):
        if sent["lang"] not in LANGS:
            raise HTTPException(422, _say("pick_lists", user.lang, items=sent["lang"]))
        user.lang = sent["lang"]

    if user.role == "farmer":
        p = db.get(FarmerProfile, user.id)
        if p is None:
            raise HTTPException(404, "no profile")
        if sent.get("district") or sent.get("state"):
            state, district = geo.match_district(sent.get("state") or p.state,
                                                 sent.get("district") or p.district)
            p.state, p.district = state, district or p.district
        for f in ("taluka", "village"):
            if f in sent:
                setattr(p, f, (sent[f] or "").strip() or None)
        if "total_land_acres" in sent:
            p.total_land_acres = sent["total_land_acres"]
    else:
        p = db.get(ExpertProfile, user.id)
        if p is None:
            raise HTTPException(404, "no profile")
        bad = [d for d in (sent.get("districts") or []) if d not in _official_districts()] \
            + [c for c in (sent.get("crops") or []) if c not in kb.crops] \
            + [x for x in (sent.get("specialities") or []) if x not in SPECIALITIES] \
            + [x for x in (sent.get("languages") or []) if x not in LANGS]
        if bad:
            raise HTTPException(422, _say("pick_lists", user.lang, items=", ".join(bad[:5])))
        # An officer's districts are not a preference, they are reach: a case
        # is routed to whoever covers the district it came from, and that case
        # carries a farmer's name, their village and photographs of their
        # field. Adding one to your own record would be granting yourself the
        # district office's permission, which is the one thing verification
        # exists to withhold. Giving a district up asks for nothing, so it is
        # yours to do; taking one on is theirs to grant, and a supervisor —
        # who may already verify officers and route a whole district — has it.
        if sent.get("districts") is not None and not services.is_supervisor(db, user):
            added = [d for d in sent["districts"] if d not in (p.districts or [])]
            if added:
                raise HTTPException(403, _say("districts_are_granted", user.lang,
                                              items=", ".join(sorted(added)[:5])))
        for f in ("districts", "crops", "specialities", "languages"):
            if sent.get(f):
                setattr(p, f, sent[f])
        for f in ("organisation", "office_address", "block", "pincode", "office_phone"):
            if f in sent:
                setattr(p, f, (sent[f] or "").strip() or None if isinstance(sent[f], str) else sent[f])
        if sent.get("experience_years") is not None:
            p.experience_years = sent["experience_years"]
    db.commit()
    return _me(db, user)


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    user = auth.current_user(request, db)
    if user is None:
        raise HTTPException(401, "not signed in")
    return _me(db, user)


@router.get("/me/data")
def my_data(request: Request, db: Session = Depends(get_db)):
    """Everything this account holds, as a file the farmer can keep.

    The Act calls it the right to access; a farmer calls it wanting to see
    what an app knows about them. Either way it is one tap in the account
    menu, not a letter to an office."""
    me = auth.signed_in(request, db)
    if me is None:
        raise HTTPException(401, "sign in first")
    data = erasure.export_account(db, me)
    name = f"annrakshak-{me.id}-{date.today().isoformat()}.json"
    return Response(content=json.dumps(data, ensure_ascii=False, indent=2),
                    media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


class EraseIn(BaseModel):
    confirm: str
    """The farmer types DELETE. A tap that cannot be undone should cost more
    than a tap."""


@router.post("/me/erase")
def erase_me(body: EraseIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Erase the person; keep the district's disease record with nobody in it.

    What goes and what stays is set out in app/erasure.py, and the answer says
    what was removed rather than only that something was."""
    me = auth.signed_in(request, db)
    if me is None:
        raise HTTPException(401, "sign in first")
    if body.confirm.strip().upper() != "DELETE":
        raise HTTPException(422, "type DELETE to confirm")
    if me.is_demo:
        raise HTTPException(403, "the demo account is shared; it is not anyone's to erase")
    removed = erasure.erase_account(db, me)
    response.delete_cookie(auth.COOKIE, path="/")
    return {"erased": True, **removed}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth.end_session(db, request.cookies.get(auth.COOKIE), response)
    db.commit()
    return {"signed_out": True}
