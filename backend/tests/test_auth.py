"""Role-aware sign-up and sign-in with emailed one-time codes, and who may see
which farm once signed in."""

import re
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config, services
from app.config import UPLOAD_DIR
from app.db import Base, SessionLocal, engine
from app.main import app
from tests.test_api import _leaf_jpeg  # the same 1x1 leaf
from app.models import (Case, Confirmation, Diagnosis, ExpertProfile, Farm, FarmerProfile, OtpChallenge,
                        Problem, PushSubscription, User, UserSession)
from app.routers import auth as auth_router

SOWN = (date.today() - timedelta(days=40)).isoformat()


@pytest.fixture()
def mail(monkeypatch):
    """Every email the app sends, instead of sending it."""
    sent: list[dict] = []

    def fake_send(to, subject, text, html_body, **_):
        sent.append({"to": to, "subject": subject, "text": text, "html": html_body})
        return "sent", None

    monkeypatch.setattr(auth_router.mailer, "send", fake_send)
    return sent


@pytest.fixture()
def client(monkeypatch, mail):
    monkeypatch.setattr(config, "AUTH_ENFORCE", True)
    monkeypatch.setattr(config, "OTP_RESEND_SECONDS", 0)
    monkeypatch.setattr(auth_router, "limit", lambda *a, **k: None)
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:
        with SessionLocal() as db:
            db.add(Farm(farmer_name="Demo", crop="rice", sowing_date=date.today() - timedelta(days=50),
                        district="Bhandara", lat=21.17, lon=79.65, is_demo=True))
            db.commit()
        yield c


def code_of(mail: list[dict]) -> str:
    return re.search(r"\b(\d{6})\b", mail[-1]["subject"]).group(1)


def farmer_signup(c: TestClient, mail, phone="9876543210", email="ramesh@example.com", **over):
    r = c.post("/api/auth/otp", json={"role": "farmer", "purpose": "signup", "email": email, "phone": phone,
                                      "lang": "mr"})
    assert r.status_code == 200, r.text
    body = {"challenge_id": r.json()["challenge_id"], "code": code_of(mail), "name": "Ramesh Patil",
            "phone": phone, "lang": "mr", "district": "Bhandara", "taluka": "Tumsar", "village": "Mohadi",
            "lat": 21.38, "lon": 79.73, "total_land_acres": 4.5, "consent": True,
            "farms": [{"crop": "rice", "variety": "Jaya", "sowing_date": SOWN, "area_acres": 2.5,
                       "irrigation": "canal", "soil_ph": 6.8}]} | over
    return c.post("/api/auth/signup/farmer", json=body)


def expert_signup(c: TestClient, mail, email="dr.kale@kvk.org.in", phone="9123456780"):
    r = c.post("/api/auth/otp", json={"role": "expert", "purpose": "signup", "email": email, "phone": phone})
    assert r.status_code == 200, r.text
    return c.post("/api/auth/signup/expert", json={
        "challenge_id": r.json()["challenge_id"], "code": code_of(mail), "name": "Dr. S. Kale", "phone": phone,
        "department": "state_agri", "office_address": "Krishi Bhavan, Civil Lines",
        "block": "Sakoli", "state": "Maharashtra", "pincode": "441802",
        "office_phone": "07184-255201", "joined_service_on": "2014-07-01",
        "posted_since": "2022-06-15", "reporting_name": "Smt. A. Deshmukh",
        "reporting_designation": "District Superintending Agriculture Officer",
        "reporting_contact": "dsao.bhandara@maha.gov.in", "declaration": True, "designation": "kvk_scientist", "organisation": "KVK Sakoli, Bhandara", "employee_id": "KVK-BH-0231",
        "department": "state_agri", "office_address": "Krishi Bhavan, Civil Lines",
        "block": "Sakoli", "state": "Maharashtra", "pincode": "441802",
        "office_phone": "07184-255201", "joined_service_on": "2014-07-01",
        "posted_since": "2022-06-15", "reporting_name": "Smt. A. Deshmukh",
        "reporting_designation": "District Superintending Agriculture Officer",
        "reporting_contact": "dsao.bhandara@maha.gov.in", "declaration": True,
        "qualification": "phd", "experience_years": 12, "districts": ["Bhandara", "Gondia"],
        "crops": ["rice", "soybean"], "specialities": ["plant_pathology"], "languages": ["mr", "hi", "en"]})


def login(c: TestClient, mail, identifier: str, role="farmer"):
    r = c.post("/api/auth/otp", json={"role": role, "purpose": "login", "identifier": identifier})
    assert r.status_code == 200, r.text
    return c.post("/api/auth/login", json={"challenge_id": r.json()["challenge_id"], "code": code_of(mail),
                                           "role": role})


def test_options_lists_the_form_choices(client):
    o = client.get("/api/auth/options").json()
    assert "Bhandara" in o["districts"] and {c["id"] for c in o["crops"]} == {"rice", "maize", "cotton", "soybean"}
    assert "canal" in o["irrigation"] and any(d["id"] == "kvk_scientist" for d in o["designations"])
    assert o["otp"]["channel"] == "email"


def test_farmer_signup_saves_profile_and_first_farm(client, mail):
    r = farmer_signup(client, mail)
    assert r.status_code == 201, r.text
    me = r.json()
    assert me["role"] == "farmer" and me["phone"] == "+919876543210" and me["email"] == "ramesh@example.com"
    assert me["profile"]["village"] == "Mohadi" and len(me["farm_ids"]) == 1
    assert mail[-1]["to"] == "ramesh@example.com"  # the code went by email, not SMS
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.phone == "+919876543210"))
        prof = db.get(FarmerProfile, user.id)
        farm = db.scalar(select(Farm).where(Farm.user_id == user.id))
        assert prof.taluka == "Tumsar" and prof.total_land_acres == 4.5 and prof.consent_at is not None
        assert (farm.crop, farm.irrigation, farm.soil_ph, farm.area_acres) == ("rice", "canal", 6.8, 2.5)
        assert (farm.lat, farm.lon, farm.taluka) == (21.38, 79.73, "Tumsar")
    assert client.get("/api/auth/me").json()["id"] == me["id"]  # the session cookie works


def test_expert_signup_asks_for_credentials_and_coverage(client, mail):
    r = expert_signup(client, mail)
    assert r.status_code == 201, r.text
    p = r.json()["profile"]
    assert p["designation"] == "kvk_scientist" and p["districts"] == ["Bhandara", "Gondia"] and p["verified"]
    with SessionLocal() as db:
        prof = db.scalar(select(ExpertProfile))
        assert (prof.employee_id, prof.qualification, prof.experience_years) == ("KVK-BH-0231", "phd", 12)
        assert db.scalar(select(Farm).where(Farm.user_id == prof.user_id)) is None  # experts own no farm


def test_codes_are_hashed_single_use_and_limited(client, mail):
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "signup", "email": "a@example.com",
                                           "phone": "9000000001"})
    cid, code = r.json()["challenge_id"], code_of(mail)
    with SessionLocal() as db:
        ch = db.scalar(select(OtpChallenge).where(OtpChallenge.public_id == cid))
        assert code not in (ch.code_hash, ch.salt)  # never stored in the clear
    wrong = "000000" if code != "000000" else "111111"
    base = {"challenge_id": cid, "name": "A B", "phone": "9000000001", "district": "Bhandara", "village": "X Y",
            "lat": 21.1, "lon": 79.6, "consent": True, "lang": "en",
            "farms": [{"crop": "rice", "sowing_date": SOWN, "area_acres": 1, "irrigation": "rainfed"}]}
    for left in (4, 3, 2, 1):
        r = client.post("/api/auth/signup/farmer", json=base | {"code": wrong})
        assert r.status_code == 400 and str(left) in r.json()["detail"]
    r = client.post("/api/auth/signup/farmer", json=base | {"code": wrong})
    assert r.status_code == 400 and "Too many" in r.json()["detail"]
    r = client.post("/api/auth/signup/farmer", json=base | {"code": code, "lang": "mr"})
    assert r.status_code == 429  # locked even with the right code now
    assert r.json()["detail"] == "खूप वेळा चुकीचा कोड टाकला. नवीन कोड मागा."  # in the farmer's language


def test_used_and_expired_codes_are_refused(client, mail):
    assert farmer_signup(client, mail).status_code == 201
    client.post("/api/auth/logout")
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "login", "identifier": "9876543210"})
    cid, code = r.json()["challenge_id"], code_of(mail)
    with SessionLocal() as db:
        ch = db.scalar(select(OtpChallenge).where(OtpChallenge.public_id == cid))
        ch.expires_at = ch.created_at - timedelta(seconds=1)
        db.commit()
    r = client.post("/api/auth/login", json={"challenge_id": cid, "code": code, "role": "farmer"})
    assert r.status_code == 400 and "expired" in r.json()["detail"]
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "login", "identifier": "9876543210"})
    body = {"challenge_id": r.json()["challenge_id"], "code": code_of(mail), "role": "farmer"}
    assert client.post("/api/auth/login", json=body).status_code == 200
    again = client.post("/api/auth/login", json=body)
    assert again.status_code == 400 and "already used" in again.json()["detail"]


def test_login_by_phone_or_email_sends_the_code_to_email(client, mail):
    assert farmer_signup(client, mail).status_code == 201
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    r = login(client, mail, "+91 98765 43210")
    assert r.status_code == 200 and mail[-1]["to"] == "ramesh@example.com"
    client.post("/api/auth/logout")
    assert login(client, mail, "RAMESH@example.com").status_code == 200


def test_login_errors_are_clear(client, mail):
    assert expert_signup(client, mail).status_code == 201
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "login", "identifier": "dr.kale@kvk.org.in"})
    assert r.status_code == 409 and "expert" in r.json()["detail"]
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "login", "identifier": "9999999999"})
    assert r.status_code == 404
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "login", "identifier": "12345"})
    assert r.status_code == 422


def test_duplicate_signups_are_refused(client, mail):
    """And say which field is at fault.

    A sign-up collects the email and the mobile number on its first step, so a
    refusal that only carries prose arrives several steps later with nothing to
    point at. The field travels with the message so the form can reopen the step
    that owns it.
    """
    assert farmer_signup(client, mail).status_code == 201
    r = client.post("/api/auth/otp", json={"role": "expert", "purpose": "signup", "email": "new@example.com",
                                           "phone": "9876543210"})
    assert r.status_code == 409
    assert r.json()["detail"]["field"] == "phone"
    assert "mobile" in r.json()["detail"]["message"]
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "signup", "email": "ramesh@example.com",
                                           "phone": "9000000009"})
    assert r.status_code == 409
    assert r.json()["detail"]["field"] == "email"
    assert "email" in r.json()["detail"]["message"]


def test_the_form_can_ask_whether_an_identifier_is_free(client, mail):
    """What /check is for: the same answer, on the step that collects them."""
    assert farmer_signup(client, mail).status_code == 201
    free = client.post("/api/auth/check", json={"email": "new@example.com", "phone": "9000000009"})
    assert free.status_code == 200 and free.json()["free"] is True and free.json()["field"] is None
    taken = client.post("/api/auth/check", json={"email": "new@example.com", "phone": "9876543210"})
    assert taken.status_code == 200
    assert taken.json()["free"] is False and taken.json()["field"] == "phone"
    assert "mobile" in taken.json()["message"]
    # A malformed identifier is still a malformed identifier.
    assert client.post("/api/auth/check", json={"email": "nope", "phone": "9000000009"}).status_code == 422


def test_signup_validates_the_answers(client, mail):
    assert farmer_signup(client, mail, consent=False).status_code == 422
    r = farmer_signup(client, mail, farms=[{"crop": "rice", "sowing_date": SOWN, "area_acres": 1,
                                           "irrigation": "sprinkler", "soil_ph": 14}])
    assert r.status_code == 422


def test_signup_registers_every_crop_a_farmer_sowed(client, mail):
    """Farmers sow more than one crop; each plot is its own field, so a photo of
    any of them is diagnosed instead of refused as 'another crop'."""
    r = farmer_signup(client, mail, farms=[
        {"crop": "rice", "sowing_date": SOWN, "area_acres": 2, "irrigation": "canal"},
        {"crop": "cotton", "sowing_date": SOWN, "area_acres": 3, "irrigation": "rainfed"},
        {"crop": "maize", "sowing_date": SOWN, "area_acres": 1.5, "irrigation": "borewell"}])
    assert r.status_code == 201, r.text
    assert len(r.json()["farm_ids"]) == 3
    with SessionLocal() as db:
        farms = db.scalars(select(Farm).where(Farm.user_id == r.json()["id"])).all()
        assert sorted(f.crop for f in farms) == ["cotton", "maize", "rice"]
        assert {f.village for f in farms} == {"Mohadi"} and {f.lat for f in farms} == {21.38}
    assert [f["crop"] for f in client.get("/api/farms").json()] == ["rice", "cotton", "maize"]


def test_a_farmer_anywhere_in_india_can_sign_up(client, mail, monkeypatch):
    """Any of the 785 districts, not one state's. Without a GPS fix the place is
    looked up, because the weather and the spray window are read at a point."""
    from app import geo

    r = farmer_signup(client, mail, state="Punjab", district="Ludhiana", village="Jagraon",
                      lat=30.79, lon=75.47)
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        farm = db.scalar(select(Farm).where(Farm.district == "Ludhiana"))
        assert (farm.state, farm.lat) == ("Punjab", 30.79)

    monkeypatch.setattr(geo, "locate", lambda state, district, village=None:
                        {"lat": 26.85, "lon": 80.95, "state": state, "district": district, "matched": village})
    r = farmer_signup(client, mail, phone="9000000022", email="two@example.com", state="Uttar Pradesh",
                      district="Lucknow", village="Malihabad", lat=None, lon=None)
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        farm = db.scalar(select(Farm).where(Farm.district == "Lucknow"))
        assert (farm.lat, farm.lon, farm.location_source) == (26.85, 80.95, "district")

    monkeypatch.setattr(geo, "locate", lambda *a, **k: None)  # nothing answers: say so, don't guess
    r = farmer_signup(client, mail, phone="9000000033", email="three@example.com", state="Bihar",
                      district="Nowhere", village="Nowhere", lat=None, lon=None, lang="en")
    assert r.status_code == 422 and "could not find" in r.json()["detail"].lower()


def test_farmers_see_only_their_own_farms(client, mail):
    assert client.get("/api/farms/1/home").status_code == 401  # signed out
    me = farmer_signup(client, mail).json()
    mine = me["farm_ids"][0]
    farms = client.get("/api/farms").json()
    assert [f["id"] for f in farms] == [mine]
    assert client.get(f"/api/farms/{mine}").status_code == 200
    assert client.get("/api/farms/1").status_code == 403  # the demo farm is not theirs
    assert client.get("/api/farms/1/weather").status_code == 403
    assert client.post("/api/labelcheck", json={"farm_id": 1, "product": "Tricyclazole"}).status_code == 403
    assert client.get("/api/cases").status_code == 403  # the expert console is for experts
    assert client.get("/api/officials/summary").status_code == 403
    r = client.post("/api/farms", json={"farmer_name": "Ramesh Patil", "crop": "maize", "sowing_date": SOWN,
                                        "district": "Bhandara", "lat": 21.3, "lon": 79.7, "area_acres": 1})
    assert r.status_code == 201
    assert len(client.get("/api/farms").json()) == 2


def test_an_officer_opens_the_farm_behind_their_own_case_and_no_other(client, mail):
    """Scoping the case list and leaving the farm open would be no scoping at
    all: the farmer's name, village, photographs and history are on that side
    of it too."""
    expert_signup(client, mail)
    other_desk = _colleague(email="third@kvk.org.in")   # its own session: not inside ours
    with SessionLocal() as db:
        me = db.scalar(select(User).where(User.email == "dr.kale@kvk.org.in"))
        mine = Farm(farmer_name="Mine", crop="rice", sowing_date=date.today() - timedelta(days=40),
                    district="Bhandara", lat=21.1, lon=79.6, area_acres=2, is_demo=False)
        theirs = Farm(farmer_name="Theirs", crop="rice", sowing_date=date.today() - timedelta(days=40),
                      district="Bhandara", lat=21.2, lon=79.7, area_acres=2, is_demo=False)
        db.add_all([mine, theirs])
        db.flush()
        for farm, holder in ((mine, me.id), (theirs, other_desk)):
            p = Problem(farm_id=farm.id, status="open")
            db.add(p)
            db.flush()
            db.add(Case(problem_id=p.id, status="open", reason="BELOW_FLOOR",
                        created_at=datetime.now(), assigned_to=holder))
        mine_id, theirs_id, my_id = mine.id, theirs.id, me.id
        # A KVK scientist is a supervisory post, and this test is about the
        # officer who is not one.
        db.get(ExpertProfile, me.id).supervisor = False
        db.commit()

    assert client.get(f"/api/farms/{mine_id}").status_code == 200
    assert client.get(f"/api/farms/{theirs_id}").status_code == 403
    assert client.get("/api/farms/1").status_code == 403          # the fixture's demo farm
    assert client.get("/api/cases").status_code == 200
    assert client.get("/api/officials/summary").status_code == 200

    with SessionLocal() as db:                                     # a supervisor opens the district
        db.get(ExpertProfile, my_id).supervisor = True
        db.commit()
    assert client.get(f"/api/farms/{theirs_id}").status_code == 200
    assert client.get("/api/farms/1").status_code == 403           # but never across the demo line

    r = client.post("/api/farms", json={"farmer_name": "X", "crop": "maize", "sowing_date": SOWN,
                                        "district": "Bhandara", "lat": 21.3, "lon": 79.7, "area_acres": 1})
    assert r.status_code == 403


def test_demo_login_opens_the_demo_farms(client):
    me = client.post("/api/auth/demo", json={"role": "farmer"}).json()
    assert me["is_demo"] and 1 in me["farm_ids"]
    assert client.get("/api/farms/1/home").status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/demo", json={"role": "expert"}).json()["role"] == "expert"
    assert client.get("/api/cases").status_code == 200


def test_logout_revokes_the_session(client, mail):
    farmer_signup(client, mail)
    token = client.cookies.get("ar_session")
    client.post("/api/auth/logout")
    client.cookies.set("ar_session", token)  # a stolen copy of the old cookie
    assert client.get("/api/auth/me").status_code == 401
    with SessionLocal() as db:
        assert db.scalar(select(UserSession)).revoked_at is not None


def test_new_sign_in_ends_the_other_browser_session(client, mail):
    farmer_signup(client, mail)
    client.post("/api/auth/logout")
    assert login(client, mail, "ramesh@example.com").status_code == 200
    first = client.cookies.get("ar_session")
    with TestClient(app) as other:  # the same account in a second browser
        assert login(other, mail, "ramesh@example.com").status_code == 200
        assert other.get("/api/auth/me").status_code == 200  # the new browser stays signed in
    client.cookies.set("ar_session", first)
    assert client.get("/api/auth/me").status_code == 401  # the old one is signed out
    with SessionLocal() as db:
        live = [s for s in db.scalars(select(UserSession)).all() if s.revoked_at is None]
        assert len(live) == 1


def test_demo_accounts_keep_every_session(client):
    """Judges share the demo account; one signing in must not sign out another."""
    assert client.post("/api/auth/demo", json={"role": "farmer"}).status_code == 200
    with TestClient(app) as other:
        assert other.post("/api/auth/demo", json={"role": "farmer"}).status_code == 200
        assert other.get("/api/auth/me").status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_session_ends_after_24_hours(client, mail):
    farmer_signup(client, mail)
    assert client.get("/api/auth/me").status_code == 200
    with SessionLocal() as db:
        s = db.scalar(select(UserSession).where(UserSession.revoked_at.is_(None)))
        assert timedelta(hours=23, minutes=59) < s.expires_at - s.created_at <= timedelta(hours=24)
        s.expires_at = s.created_at - timedelta(seconds=1)  # as if 24 hours have passed
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_older_long_sessions_also_end_at_24_hours(client, mail):
    """A session issued with the old 30-day lifetime still ends 24 h after sign-in."""
    farmer_signup(client, mail)
    with SessionLocal() as db:
        s = db.scalar(select(UserSession).where(UserSession.revoked_at.is_(None)))
        s.created_at -= timedelta(hours=25)
        s.expires_at = s.created_at + timedelta(days=30)
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def _real_case(district="Bhandara"):
    """A case on a real farmer's field, with a real officer covering it."""
    from app.models import Case, Diagnosis, ExpertProfile, Farm, Problem, User
    with SessionLocal() as db:
        farm = Farm(farmer_name="Real farmer", crop="rice", district=district,
                    sowing_date=date.today() - timedelta(days=50), lat=21.17, lon=79.65)
        db.add(farm)
        db.flush()
        p = Problem(farm_id=farm.id, status="open")
        db.add(p)
        db.flush()
        db.add(Diagnosis(problem_id=p.id, topk=[{"target": "rice_brown_spot", "confidence": 0.5}],
                         gate_outcome="escalate", gate_reason="BELOW_GATE", confidence=0.5,
                         model_version="test", is_stub=True))
        c = Case(problem_id=p.id, status="open", reason="BELOW_GATE")
        db.add(c)
        db.flush()
        case_id = c.id
        db.commit()
    return case_id


def test_a_demo_reviewer_never_sees_a_real_farmers_case(client, mail):
    """Whoever tapped 'try the demo' is not shown a real farmer's field."""
    case_id = _real_case()
    assert client.post("/api/auth/demo", json={"role": "expert"}).status_code == 200
    assert client.get("/api/cases?status=open&scope=all").json() == []
    assert client.get(f"/api/cases/{case_id}").status_code == 404      # not by id either
    assert client.post(f"/api/cases/{case_id}/reassign", json={}).status_code == 404
    assert client.post(f"/api/cases/{case_id}/resolve", json={
        "verdict": "confirmed", "final_label": "rice_brown_spot",
        "expert_name": "Demo expert"}).status_code == 404


def _expert(client, mail, *, verified: bool, supervisor: bool = False,
            email="new.officer@kvk.org.in", phone="9000000001"):
    """A signed-up officer in whatever state the district office left them."""
    r = client.post("/api/auth/otp", json={"role": "expert", "purpose": "signup",
                                           "email": email, "phone": phone})
    client.post("/api/auth/signup/expert", json={
        "challenge_id": r.json()["challenge_id"], "code": code_of(mail), "name": "New Officer",
        "phone": phone, "designation": "agri_officer", "organisation": "DAO",
        "employee_id": "E-1",
        "department": "state_agri", "office_address": "Krishi Bhavan, Civil Lines",
        "block": "Sakoli", "state": "Maharashtra", "pincode": "441802",
        "office_phone": "07184-255201", "joined_service_on": "2014-07-01",
        "posted_since": "2022-06-15", "reporting_name": "Smt. A. Deshmukh",
        "reporting_designation": "District Superintending Agriculture Officer",
        "reporting_contact": "dsao.bhandara@maha.gov.in", "declaration": True,
        "qualification": "bsc_agri", "experience_years": 3,
        "districts": ["Bhandara"], "crops": ["rice"], "specialities": ["entomology"],
        "languages": ["mr"]})
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        prof = db.get(ExpertProfile, user.id)
        prof.verified, prof.supervisor = verified, supervisor
        db.commit()
        return user.id


def test_an_unverified_officer_reviews_nothing(client, mail):
    """Verification used to be a label. An unverified sign-up could open a real
    farmer's case and file a verdict on it."""
    _expert(client, mail, verified=False)
    case_id = _real_case()
    assert client.get("/api/cases?status=open").status_code == 403
    assert client.get(f"/api/cases/{case_id}").status_code == 403
    assert client.post(f"/api/cases/{case_id}/resolve", json={
        "verdict": "confirmed", "final_label": "rice_brown_spot",
        "expert_name": "New Officer"}).status_code == 403
    assert client.get("/api/officials/summary").status_code == 403


def test_an_officer_cannot_verify_themselves(client, mail):
    """The whole point of verification is that somebody else did it."""
    uid = _expert(client, mail, verified=True, supervisor=True)
    r = client.post(f"/api/officials/officers/{uid}/verify", json={"verified": True})
    assert r.status_code == 409 and "own account" in r.json()["detail"]


def _colleague(name="Colleague", email="second@kvk.org.in", demo=False) -> int:
    """Another officer on the books — made directly, so the caller keeps their session."""
    with SessionLocal() as db:
        u = User(role="expert", name=name, email=email, is_demo=demo)
        db.add(u)
        db.flush()
        db.add(ExpertProfile(user_id=u.id, designation="agri_officer", organisation="DAO",
                             employee_id="E-2", qualification="bsc_agri", experience_years=4,
                             districts=["Bhandara"], crops=["rice"], specialities=[], languages=["mr"],
                             verified=False))
        db.commit()
        return u.id


def test_verifying_and_routing_are_supervisor_work(client, mail):
    uid = _expert(client, mail, verified=True, supervisor=False)
    other = _colleague()
    assert uid != other
    assert client.post(f"/api/officials/officers/{other}/verify", json={"verified": True}).status_code == 403
    assert client.post("/api/officials/cases/route").status_code == 403
    assert client.post("/api/cases/bulk/assign", json={"case_ids": [1]}).status_code == 403
    # A verified officer still does their own job.
    assert client.get("/api/cases?status=open").status_code == 200


def test_a_supervisor_cannot_reach_across_the_demo_line(client, mail):
    """A showcase supervisor has no business over a real district's staff."""
    real = _expert(client, mail, verified=False)
    client.post("/api/auth/logout")
    client.post("/api/auth/demo", json={"role": "expert"})    # demo supervisor
    assert client.post(f"/api/officials/officers/{real}/verify", json={"verified": True}).status_code == 404
    with SessionLocal() as db:
        assert db.get(ExpertProfile, real).verified is False


def test_the_office_keeps_a_record_of_who_did_what(client, mail):
    uid = _expert(client, mail, verified=False)
    client.post("/api/auth/logout")
    client.post("/api/auth/demo", json={"role": "expert"})
    with SessionLocal() as db:          # make the new officer demo-side so the demo supervisor may act
        db.get(User, uid).is_demo = True
        db.commit()
    assert client.post(f"/api/officials/officers/{uid}/verify", json={"verified": True}).status_code == 200
    log = client.get("/api/officials/actions").json()
    assert log[0]["action"] == "verify_officer"
    assert log[0]["subject_id"] == uid and log[0]["actor"] == "Demo expert"


def test_a_bulk_move_cannot_reach_across_the_demo_line(client, mail):
    """The boundary holds for a selection, not only for one case at a time."""
    case_id = _real_case()
    assert client.post("/api/auth/demo", json={"role": "expert"}).status_code == 200
    out = client.post("/api/cases/bulk/assign", json={"case_ids": [case_id], "to_user_id": None}).json()
    assert out == {"moved": 0, "skipped": 1}


def test_a_real_officer_is_not_shown_showcase_data(client, mail):
    """The boundary holds both ways: demo farms are not a real officer's work."""
    assert expert_signup(client, mail).status_code == 201
    listed = client.get("/api/cases?status=open&scope=all").json()
    assert listed == []  # the only farm in this fixture is the demo one
    case_id = _real_case()
    assert [c["id"] for c in client.get("/api/cases?status=open&scope=all").json()] == [case_id]


def test_a_real_farmers_case_is_never_routed_to_a_demo_officer(client, mail):
    from app.models import Case
    client.post("/api/auth/demo", json={"role": "expert"})   # a demo officer exists and is verified
    case_id = _real_case()
    with SessionLocal() as db:
        case = db.get(Case, case_id)
        farm = db.get(Problem, case.problem_id).farm
        picked = services.assign_case(db, case, farm)
        db.commit()
    assert picked is None  # no real officer yet, and the demo one is not eligible


def test_a_farmers_photo_is_not_served_to_a_stranger(client, mail):
    """The photo is of someone's field. A URL that leaks — a screenshot, a log,
    a shared link — must not be the photograph itself."""
    farmer_signup(client, mail)
    me = client.get("/api/auth/me").json()
    farm_id = me["farm_ids"][0]
    r = client.post(f"/api/farms/{farm_id}/diagnose",
                    files={"image": ("x.jpg", _leaf_jpeg(), "image/jpeg")},
                    data={"lang": "en", "demo_scenario": "clear"}).json()
    url = r.get("image_url")
    assert url and url.startswith("/media/")
    assert client.get(url).status_code == 200          # its own farmer

    with TestClient(app) as stranger:                  # nobody at all
        assert stranger.get(url).status_code == 404
        # a second farmer, signed in, still may not have it
        farmer_signup(stranger, mail, phone="9876500001", email="other@example.com")
        assert stranger.get(url).status_code == 404
        # an officer may — but only one the district office has verified. An
        # account that signed up as an expert two minutes ago is not that.
        expert_signup(stranger, mail)
        with SessionLocal() as db:
            prof = db.scalar(select(ExpertProfile).join(User, User.id == ExpertProfile.user_id)
                             .where(User.email == "dr.kale@kvk.org.in"))
            prof.verified = False
            db.commit()
        assert stranger.get(url).status_code == 404
        with SessionLocal() as db:
            prof = db.scalar(select(ExpertProfile).join(User, User.id == ExpertProfile.user_id)
                             .where(User.email == "dr.kale@kvk.org.in"))
            prof.verified = True
            db.commit()
        assert stranger.get(url).status_code == 200
    assert client.get("/media/../../etc/passwd").status_code in (404, 400)


def test_voice_needs_a_signed_in_user(client):
    assert client.post("/api/voice/tts", json={"text": "hello", "lang": "en"}).status_code == 401


def test_live_walk_refuses_someone_elses_farm(client, mail):
    farmer_signup(client, mail)
    with client.websocket_connect("/api/live/1") as ws:
        assert ws.receive_json() == {"type": "error", "code": "NOT_ALLOWED"}


def test_verdict_carries_the_signed_in_expert(client, mail):
    """The expert console no longer asks who is reviewing: the server takes the
    name from the session, so a verdict cannot be filed under someone else."""
    from app.models import Case, Confirmation, Diagnosis, Problem

    with SessionLocal() as db:
        # A real farmer's field: a signed-up expert never reviews demo data.
        farm = Farm(farmer_name="Real", crop="rice", sowing_date=date.today() - timedelta(days=50),
                    district="Bhandara", lat=21.17, lon=79.65)
        db.add(farm)
        db.flush()
        p = Problem(farm_id=farm.id, target="rice_brown_spot", status="open")
        db.add(p)
        db.flush()
        db.add(Diagnosis(problem_id=p.id, topk=[{"target": "rice_brown_spot", "confidence": 0.5}],
                         gate_outcome="escalate", gate_reason="BELOW_GATE", confidence=0.5,
                         model_version="test", is_stub=True))
        db.add(Case(problem_id=p.id, status="open", reason="BELOW_GATE"))
        db.commit()
        case_id = db.scalar(select(Case.id))
    assert expert_signup(client, mail).status_code == 201
    r = client.post(f"/api/cases/{case_id}/resolve", json={
        "verdict": "confirmed", "final_label": "rice_brown_spot", "expert_name": "Somebody Else"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.scalar(select(Confirmation)).expert_name == "Dr. S. Kale"


def test_sample_photos_are_for_demo_accounts_only(client, mail):
    """A farmer who signed up for their own field is looking at their own crop.
    Somebody else's photos must not appear on their Scan screen, and asking the
    API directly must not get them either."""
    farmer_signup(client, mail)
    assert client.get("/api/samples").json() == []
    client.post("/api/auth/logout")
    assert client.get("/api/samples").json() == []  # signed out too
    client.post("/api/auth/demo", json={"role": "farmer"})
    assert client.get("/api/samples").status_code == 200  # the demo account may have them


def test_the_post_decides_the_supervisor_rank(client, mail):
    """The bug this guards: every sign-up was an ordinary desk.

    `supervisor` was never set on sign-up, so a district whose officers had all
    signed up had nobody who could route its backlog, verify the next arrival
    or move another desk's cases -- the server refused all three for everyone.
    The rank follows the post, and travels in /me so a screen can offer only
    what this desk may actually do.
    """
    r = expert_signup(client, mail)
    assert r.status_code == 201, r.text
    assert r.json()["profile"]["supervisor"] is True          # a KVK scientist
    assert r.json()["profile"]["designation_name"] == "KVK scientist / Subject Matter Specialist"

    r = client.post("/api/auth/otp", json={"role": "expert", "purpose": "signup",
                                           "email": "sahayak@kvk.org.in", "phone": "9123456781"})
    assert r.status_code == 200, r.text
    r = client.post("/api/auth/signup/expert", json={
        "challenge_id": r.json()["challenge_id"], "code": code_of(mail), "name": "R. Ingle",
        "phone": "9123456781", "designation": "agri_assistant", "organisation": "Taluka Agri Office",
        "employee_id": "MH-AA-77", "department": "state_agri",
        "office_address": "Taluka Agri Office, Sakoli", "state": "Maharashtra", "pincode": "441802",
        "reporting_name": "Shri P. Rathod", "reporting_designation": "Taluka Agriculture Officer",
        "reporting_contact": "tao.sakoli@maha.gov.in", "declaration": True,
        "qualification": "bsc_agri", "experience_years": 4,
        "districts": ["Bhandara"], "crops": ["rice"], "specialities": ["agronomy"], "languages": ["mr"]})
    assert r.status_code == 201, r.text
    assert r.json()["profile"]["supervisor"] is False         # an assistant advises


def test_an_older_profile_is_given_its_rank_and_a_readable_post(client):
    """The backfill. `supervisor` and the designation list both arrived after the
    demo districts were seeded, so in a database made before them no account was
    a supervisor and the designation rendered blank."""
    from sqlalchemy import select

    from app.db import SessionLocal, _backfill_expert_ranks, engine
    from app.models import ExpertProfile, User

    with SessionLocal() as db:
        u = User(role="expert", name="Old Row", email="old@kvk.test", is_demo=True)
        db.add(u)
        db.flush()
        db.add(ExpertProfile(user_id=u.id, designation="agriculture_officer", organisation="DAO",
                             employee_id="E9", qualification="msc_agri", experience_years=11,
                             districts=["Bhandara"], crops=["rice"], specialities=[], languages=["mr"],
                             verified=True, supervisor=False))
        db.commit()
        uid = u.id

    _backfill_expert_ranks(engine)

    with SessionLocal() as db:
        p = db.scalar(select(ExpertProfile).where(ExpertProfile.user_id == uid))
        assert p.designation == "agri_officer"   # renamed into the vocabulary
        assert p.supervisor is True              # and given the rank its post carries


def test_an_officer_outside_maharashtra_can_sign_up(client, mail):
    """The form offers every district the Government publishes. The check used
    to run against the IMD rainfall map — 36 Maharashtra districts — so an
    officer in Punjab picked two districts out of the form's own list and was
    told to choose from the list."""
    r = client.post("/api/auth/otp", json={"role": "expert", "purpose": "signup",
                                           "email": "dr.bob@kvk.org.in", "phone": "9123456788"})
    r = client.post("/api/auth/signup/expert", json={
        "challenge_id": r.json()["challenge_id"], "code": code_of(mail), "name": "Dr. Bob",
        "phone": "9123456788", "department": "state_agri", "office_address": "Krishi Bhavan, Civil Lines",
        "block": "Sakoli", "state": "Maharashtra", "pincode": "441802",
        "office_phone": "07184-255201", "joined_service_on": "2014-07-01",
        "posted_since": "2022-06-15", "reporting_name": "Smt. A. Deshmukh",
        "reporting_designation": "District Superintending Agriculture Officer",
        "reporting_contact": "dsao.bhandara@maha.gov.in", "declaration": True, "designation": "kvk_scientist", "organisation": "KVK Kapurthala, Punjab",
        "employee_id": "KVKPT001", "qualification": "bsc_agri", "experience_years": 13,
        "districts": ["Hoshiarpur", "Kapurthala"], "crops": ["rice"],
        "specialities": ["plant_pathology"], "languages": ["en", "hi"]})
    assert r.status_code == 201, r.text
    assert r.json()["profile"]["districts"] == ["Hoshiarpur", "Kapurthala"]


def test_a_district_nobody_publishes_is_still_refused(client, mail):
    """The list is still a list: the check moved to the right one, it did not
    stop checking."""
    r = client.post("/api/auth/otp", json={"role": "expert", "purpose": "signup",
                                           "email": "dr.nowhere@kvk.org.in", "phone": "9123456787"})
    r = client.post("/api/auth/signup/expert", json={
        "challenge_id": r.json()["challenge_id"], "code": code_of(mail), "name": "Dr. Nowhere",
        "phone": "9123456787", "department": "state_agri", "office_address": "Krishi Bhavan, Civil Lines",
        "block": "Sakoli", "state": "Maharashtra", "pincode": "441802",
        "office_phone": "07184-255201", "joined_service_on": "2014-07-01",
        "posted_since": "2022-06-15", "reporting_name": "Smt. A. Deshmukh",
        "reporting_designation": "District Superintending Agriculture Officer",
        "reporting_contact": "dsao.bhandara@maha.gov.in", "declaration": True, "designation": "kvk_scientist", "organisation": "KVK",
        "employee_id": "X-1", "qualification": "bsc_agri", "experience_years": 1,
        "districts": ["Atlantis"], "crops": ["rice"],
        "specialities": ["plant_pathology"], "languages": ["en"]})
    assert r.status_code == 422
    assert "Atlantis" in r.json()["detail"]


def test_an_officers_own_states_travel_with_their_profile(client, mail):
    """The console says where this officer is watching, and it used to say
    Maharashtra to everyone. The states are read off the districts they cover."""
    r = client.post("/api/auth/otp", json={"role": "expert", "purpose": "signup",
                                           "email": "dr.rain@kvk.org.in", "phone": "9123456786"})
    r = client.post("/api/auth/signup/expert", json={
        "challenge_id": r.json()["challenge_id"], "code": code_of(mail), "name": "Dr. Rain",
        "phone": "9123456786", "department": "state_agri", "office_address": "Krishi Bhavan, Civil Lines",
        "block": "Sakoli", "state": "Maharashtra", "pincode": "441802",
        "office_phone": "07184-255201", "joined_service_on": "2014-07-01",
        "posted_since": "2022-06-15", "reporting_name": "Smt. A. Deshmukh",
        "reporting_designation": "District Superintending Agriculture Officer",
        "reporting_contact": "dsao.bhandara@maha.gov.in", "declaration": True, "designation": "kvk_scientist", "organisation": "KVK Kapurthala",
        "employee_id": "KVKPT002", "qualification": "bsc_agri", "experience_years": 4,
        "districts": ["Hoshiarpur", "Kapurthala"], "crops": ["rice"],
        "specialities": ["plant_pathology"], "languages": ["en"]})
    assert r.status_code == 201, r.text
    assert r.json()["profile"]["states"] == ["Punjab"]


def test_a_farmer_can_take_their_data_and_have_it_erased(client, mail):
    """Consent at sign-up is half a bargain. The other half is being able to
    see what the app holds, and to have the person in it erased."""
    farmer_signup(client, mail)
    me = client.get("/api/auth/me").json()
    farm_id = me["farm_ids"][0]
    r = client.post(f"/api/farms/{farm_id}/diagnose",
                    files={"image": ("x.jpg", _leaf_jpeg(), "image/jpeg")},
                    data={"lang": "en", "demo_scenario": "clear"}).json()
    photo = (r.get("image_url") or "").removeprefix("/media/")

    # Everything we hold, in their hands.
    out = client.get("/api/auth/me/data")
    assert out.status_code == 200 and "attachment" in out.headers["content-disposition"]
    data = out.json()
    assert data["account"]["phone"] == "+919876543210"
    assert data["farms"][0]["crop"] == "rice" and data["profile"]["village"] == "Mohadi"
    assert data["photographs"] and data["photographs"][0]["file"] == photo

    assert client.post("/api/auth/me/erase", json={"confirm": "no"}).status_code == 422

    gone = client.post("/api/auth/me/erase", json={"confirm": "DELETE"})
    assert gone.status_code == 200 and gone.json()["photographs"] == 1
    assert client.get("/api/auth/me").status_code == 401        # the session went with them

    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.phone == "+919876543210")) is None
        farm = db.get(Farm, farm_id)
        assert farm is not None                                  # the district keeps its record
        assert farm.farmer_name == "(erased)" and farm.user_id is None
        assert farm.village is None and farm.phone is None
        assert db.scalar(select(Diagnosis).where(Diagnosis.image_path.is_not(None))) is None
    assert not (UPLOAD_DIR / photo).exists()                     # the file, not only the row


def _case_on(desk_id: int | None) -> int:
    """An open case on a real farm, optionally already on somebody's desk.

    Real, not the fixture's demo farm: an officer who signed up here is a real
    account, and the two sides never see each other's cases."""
    with SessionLocal() as db:
        farm = db.scalar(select(Farm).where(Farm.is_demo.is_(False)))
        if farm is None:
            farm = Farm(farmer_name="Ramesh", crop="rice",
                        sowing_date=date.today() - timedelta(days=40), district="Bhandara",
                        lat=21.17, lon=79.65, area_acres=2, is_demo=False)
            db.add(farm)
            db.flush()
        p = Problem(farm_id=farm.id, status="open")
        db.add(p)
        db.flush()
        c = Case(problem_id=p.id, status="open", reason="BELOW_FLOOR",
                 created_at=datetime.now(), assigned_to=desk_id)
        db.add(c)
        db.commit()
        return c.id


def test_an_officer_sees_their_own_desk_and_not_a_colleagues(client, mail):
    """A case carries a farmer's name, their village and photographs of their
    field. A district's staff have no reason to read one another's."""
    me = _expert(client, mail, verified=True, supervisor=False)
    other = _colleague()
    mine, theirs = _case_on(me), _case_on(other)

    listed = [c["id"] for c in client.get("/api/cases?status=open").json()]
    assert mine in listed and theirs not in listed
    assert client.get(f"/api/cases/{mine}").status_code == 200
    assert client.get(f"/api/cases/{theirs}").status_code == 404   # not 403: not theirs to know of
    # Asking for the whole queue does not widen it.
    assert theirs not in [c["id"] for c in client.get("/api/cases?status=open&scope=all").json()]


def test_a_supervisor_sees_the_whole_queue(client, mail):
    boss = _expert(client, mail, verified=True, supervisor=True)
    other = _colleague()
    mine, theirs = _case_on(boss), _case_on(other)
    listed = [c["id"] for c in client.get("/api/cases?status=open&scope=all").json()]
    assert mine in listed and theirs in listed
    assert client.get(f"/api/cases/{theirs}").status_code == 200


def test_only_a_supervisor_places_a_case_by_name(client, mail):
    """The system routes cases. An officer may give one up; they may not decide
    whose desk it lands on, and they cannot read the roster to choose from."""
    _expert(client, mail, verified=True, supervisor=False)
    other = _colleague()
    case_id = _case_on(None)
    assert client.post(f"/api/cases/{case_id}/reassign",
                       json={"to_user_id": other}).status_code == 403
    assert client.get("/api/cases/officers/list").status_code == 403
    # Handing it back to the system is theirs to do.
    assert client.post(f"/api/cases/{case_id}/reassign", json={}).status_code == 200


def test_district_wide_writes_are_supervisor_work(client, mail):
    """Each of these reaches every farm in the district: alerts raised, phones
    woken, email sent. They were open to any verified officer, and the watcher
    sweep to any signed-in account at all."""
    _expert(client, mail, verified=True, supervisor=False)
    assert client.post("/api/officials/risk/run-all").status_code == 403
    assert client.post("/api/officials/watch/run").status_code == 403


def test_a_farmer_cannot_start_a_district_sweep(client, mail):
    farmer_signup(client, mail)
    assert client.post("/api/officials/watch/run").status_code == 403
    assert client.post("/api/officials/risk/run-all").status_code == 403


def _expert_body(mail, challenge_id, **over) -> dict:
    """A complete officer sign-up, as the form sends it."""
    return {
        "challenge_id": challenge_id, "code": code_of(mail), "name": "Dr. S. Kale",
        "phone": "9123456700", "designation": "agri_officer", "department": "state_agri",
        "organisation": "District Agriculture Office, Bhandara", "employee_id": "MH-DAO-118",
        "office_address": "Krishi Bhavan, Civil Lines", "block": "Sakoli",
        "state": "Maharashtra", "pincode": "441802", "office_phone": "07184-255201",
        "joined_service_on": "2014-07-01", "posted_since": "2022-06-15",
        "reporting_name": "Smt. A. Deshmukh",
        "reporting_designation": "District Superintending Agriculture Officer",
        "reporting_contact": "dsao.bhandara@maha.gov.in", "declaration": True,
        "qualification": "msc_agri", "experience_years": 11, "districts": ["Bhandara"],
        "crops": ["rice"], "specialities": ["entomology"], "languages": ["mr", "en"],
    } | over


def test_an_officer_gives_the_office_what_it_needs_to_check_them(client, mail):
    """A farmer is asked the least that lets the app help them. An officer is
    asking to read other people's fields, so the office is given enough to
    check who they are — including somebody to ring."""
    r = client.post("/api/auth/otp", json={"role": "expert", "purpose": "signup",
                                           "email": "kale2@kvk.org.in", "phone": "9123456700"})
    out = client.post("/api/auth/signup/expert",
                      json=_expert_body(mail, r.json()["challenge_id"]))
    assert out.status_code == 201, out.text
    with SessionLocal() as db:
        p = db.scalar(select(ExpertProfile).join(User, User.id == ExpertProfile.user_id)
                      .where(User.email == "kale2@kvk.org.in"))
        assert p.department == "state_agri" and p.pincode == "441802"
        assert p.office_address.startswith("Krishi Bhavan")
        assert p.reporting_name == "Smt. A. Deshmukh"
        assert p.joined_service_on.year == 2014 and p.posted_since.year == 2022
        assert p.declared_at is not None


def test_the_undertaking_and_the_office_details_are_not_optional(client, mail):
    def signup(email, phone, **over):
        r = client.post("/api/auth/otp", json={"role": "expert", "purpose": "signup",
                                               "email": email, "phone": phone})
        return client.post("/api/auth/signup/expert",
                           json=_expert_body(mail, r.json()["challenge_id"], phone=phone, **over))

    assert signup("a@kvk.org.in", "9123456701", declaration=False).status_code == 422
    assert signup("b@kvk.org.in", "9123456702", pincode="12").status_code == 422
    assert signup("c@kvk.org.in", "9123456703", department="not_a_department").status_code == 422
    assert signup("d@kvk.org.in", "9123456704", reporting_contact="").status_code == 422


def test_the_dossier_and_the_map_follow_the_same_rule_as_the_case(client, mail):
    """Every door into a farm is the same door. The dossier wrote its own check
    and the map carried farmers' names to anyone who could see a pin."""
    expert_signup(client, mail)
    other_desk = _colleague(email="fourth@kvk.org.in")
    with SessionLocal() as db:
        me = db.scalar(select(User).where(User.email == "dr.kale@kvk.org.in"))
        db.get(ExpertProfile, me.id).supervisor = False
        farm = Farm(farmer_name="Someone Else", crop="rice",
                    sowing_date=date.today() - timedelta(days=40), district="Bhandara",
                    lat=21.2, lon=79.7, area_acres=2, is_demo=False)
        db.add(farm)
        db.flush()
        p = Problem(farm_id=farm.id, status="open", target="rice_brown_spot",
                    opened_at=datetime.now())
        db.add(p)
        db.flush()
        db.add(Case(problem_id=p.id, status="open", reason="BELOW_FLOOR",
                    created_at=datetime.now(), assigned_to=other_desk))
        db.add(Confirmation(problem_id=p.id, verdict="confirmed", final_label="rice_brown_spot",
                            expert_name="Someone", created_at=datetime.now()))
        farm_id, my_id = farm.id, me.id
        db.commit()

    # 403 from the router's own path guard, which now asks the same question
    assert client.get(f"/api/officials/farms/{farm_id}").status_code == 403
    pins = client.get("/api/officials/hotspots").json()["points"]
    mine = [p for p in pins if p["district"] == "Bhandara"]
    assert mine, "the outbreak is still on the map"
    assert all(p["farmer_name"] is None for p in mine), "but not whose field it is"

    with SessionLocal() as db:
        db.get(ExpertProfile, my_id).supervisor = True
        db.commit()
    assert client.get(f"/api/officials/farms/{farm_id}").status_code == 200
    named = client.get("/api/officials/hotspots").json()["points"]
    assert any(p["farmer_name"] == "Someone Else" for p in named)


def test_the_sign_in_widget_guards_the_request_for_a_code(client, mail, monkeypatch):
    """Both sign-up and login start by asking for a code, which costs money and
    reaches a real inbox, so one check covers both screens."""
    from app import turnstile
    from app.routers import auth as auth_router

    seen: list[str | None] = []

    def refuse(token, ip=None):
        seen.append(token)
        return False, "invalid-input-response"

    monkeypatch.setattr(auth_router.turnstile, "verify", refuse)
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "signup",
                                           "email": "x@example.com", "phone": "9876500099",
                                           "turnstile_token": "a-bad-token"})
    assert r.status_code == 403 and "check" in r.json()["detail"]
    assert seen == ["a-bad-token"], "the token reaches the verifier"
    assert not mail, "and no code is sent"

    monkeypatch.setattr(auth_router.turnstile, "verify", lambda token, ip=None: (True, None))
    assert client.post("/api/auth/otp", json={"role": "farmer", "purpose": "signup",
                                              "email": "x@example.com", "phone": "9876500099",
                                              "turnstile_token": "a-good-token"}).status_code == 200

    # Cloudflare unreachable: the request goes through rather than locking a
    # farmer out, because the emailed code is still the real door.
    def explode(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr(turnstile, "configured", lambda: True)
    monkeypatch.setattr(turnstile.httpx, "post", explode)
    assert turnstile.verify("whatever", "1.2.3.4") == (True, None)


def test_with_no_keys_there_is_no_box_and_nothing_to_pass(client):
    """Blank keys take the widget off: the API says so, and a code can still be
    asked for."""
    from app import turnstile

    assert turnstile.configured() is False
    assert client.get("/api/auth/options").json()["turnstile_sitekey"] is None
    assert turnstile.verify(None) == (True, None)


def test_a_farmer_can_correct_their_own_details(client, mail):
    """One door for both roles: your own record, yours to change."""
    farmer_signup(client, mail)
    r = client.patch("/api/auth/me/profile", json={"name": "Ramesh K. Patil", "village": "Sakoli",
                                                   "total_land_acres": 3.5, "lang": "mr"})
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["name"] == "Ramesh K. Patil" and me["lang"] == "mr"
    assert me["profile"]["village"] == "Sakoli" and me["profile"]["total_land_acres"] == 3.5
    # Sending one line does not blank the rest.
    assert me["profile"]["district"]


def test_an_officer_cannot_grant_themselves_another_district(client, mail):
    """Coverage is reach, not preference.

    A case is routed to whoever covers the district it came from, and it
    carries a farmer's name, their village and photographs of their field. An
    officer who could add a district to their own record would be granting
    themselves the district office's permission — which is the one thing
    verification exists to withhold."""
    # An agriculture assistant: verified, and not a supervisor.
    _expert(client, mail, verified=True, supervisor=False)   # covers Bhandara

    grab = client.patch("/api/auth/me/profile", json={"districts": ["Bhandara", "Mumbai"]})
    assert grab.status_code == 403, grab.text
    assert "Mumbai" in grab.json()["detail"]
    assert client.get("/api/auth/me").json()["profile"]["districts"] == ["Bhandara"]

    # Giving one up asks for nothing, so it stays theirs to do.
    drop = client.patch("/api/auth/me/profile", json={"districts": []})
    assert drop.status_code == 200, drop.text


def test_a_supervisor_may_take_on_a_district(client, mail):
    """A supervisor already verifies officers and routes a district's backlog;
    withholding this from them would be a lock with the key beside it."""
    expert_signup(client, mail)   # a KVK scientist: supervisor by post
    assert client.get("/api/auth/me").json()["profile"]["supervisor"] is True
    r = client.patch("/api/auth/me/profile", json={"districts": ["Bhandara", "Gondia", "Nagpur"]})
    assert r.status_code == 200, r.text
    assert "Nagpur" in r.json()["profile"]["districts"]


def test_the_record_the_office_checked_is_not_self_service(client, mail):
    """The reporting line and the sign-in phone are what the office verified
    this person against. A record its holder can rewrite is not evidence."""
    expert_signup(client, mail)
    before = client.get("/api/auth/me").json()
    r = client.patch("/api/auth/me/profile", json={
        "organisation": "KVK Sakoli", "reporting_name": "Nobody", "phone": "9000000009"})
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["profile"]["organisation"] == "KVK Sakoli", "the office address is theirs to correct"
    assert after["profile"]["reporting_name"] == before["profile"]["reporting_name"]
    assert after["phone"] == before["phone"]

def test_a_spray_check_cannot_name_somebody_elses_problem(client, mail):
    """The problem id travels in the body, where the router's ownership check
    cannot see it. Naming a stranger's problem would answer which disease is on
    their field — the one thing a farmer's record is meant to keep."""
    farmer_signup(client, mail)
    mine = client.get("/api/auth/me").json()["farm_ids"][0]
    client.post(f"/api/farms/{mine}/diagnose", files={"image": ("x.jpg", _leaf_jpeg(), "image/jpeg")},
                data={"lang": "en", "demo_scenario": "clear"})
    with SessionLocal() as db:
        theirs = db.scalar(select(Problem).where(Problem.farm_id == mine))
    assert theirs is not None and theirs.target

    with TestClient(app) as other:
        farmer_signup(other, mail, phone="9876500002", email="nosy@example.com")
        their_farm = other.get("/api/auth/me").json()["farm_ids"][0]
        r = other.post("/api/labelcheck", json={"farm_id": their_farm, "product": "carbendazim",
                                                "problem_id": theirs.id})
        assert r.status_code == 404
        # And the farm it does own still answers.
        assert other.post("/api/labelcheck", json={"farm_id": their_farm,
                                                   "product": "carbendazim"}).status_code == 200


def test_a_stranger_cannot_silence_a_farmers_phone(client, mail):
    """Unsubscribing takes the endpoint in the body, so the router never checks
    it. It used to delete whatever row matched, for anyone who asked."""
    farmer_signup(client, mail)
    farm_id = client.get("/api/auth/me").json()["farm_ids"][0]
    endpoint = "https://fcm.googleapis.com/fcm/send/a-real-phone"
    assert client.post(f"/api/farms/{farm_id}/push/subscribe",
                       json={"endpoint": endpoint,
                             "keys": {"p256dh": "B" * 60, "auth": "a" * 16}}).status_code == 201

    with TestClient(app) as stranger:  # nobody at all
        assert stranger.post("/api/push/unsubscribe", json={"endpoint": endpoint}).status_code == 401
        farmer_signup(stranger, mail, phone="9876500003", email="other2@example.com")
        assert stranger.post("/api/push/unsubscribe", json={"endpoint": endpoint}).status_code == 404
    with SessionLocal() as db:
        assert db.query(PushSubscription).count() == 1, "the phone is still subscribed"

    assert client.post("/api/push/unsubscribe", json={"endpoint": endpoint}).status_code == 200
    with SessionLocal() as db:
        assert db.query(PushSubscription).count() == 0
