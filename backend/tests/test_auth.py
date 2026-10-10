"""Role-aware sign-up and sign-in with emailed one-time codes, and who may see
which farm once signed in."""

import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config, services
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import ExpertProfile, Farm, FarmerProfile, OtpChallenge, Problem, User, UserSession
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
        "designation": "kvk_scientist", "organisation": "KVK Sakoli, Bhandara", "employee_id": "KVK-BH-0231",
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


def test_experts_open_any_farm_and_the_consoles(client, mail):
    expert_signup(client, mail)
    assert client.get("/api/farms/1").status_code == 200
    assert client.get("/api/cases").status_code == 200
    assert client.get("/api/officials/summary").status_code == 200
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
        "employee_id": "E-1", "qualification": "bsc_agri", "experience_years": 3,
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
        "employee_id": "MH-AA-77", "qualification": "bsc_agri", "experience_years": 4,
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
