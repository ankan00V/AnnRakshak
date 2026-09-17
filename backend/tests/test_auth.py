"""Role-aware sign-up and sign-in with emailed one-time codes, and who may see
which farm once signed in."""

import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import ExpertProfile, Farm, FarmerProfile, OtpChallenge, User, UserSession
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
    assert farmer_signup(client, mail).status_code == 201
    r = client.post("/api/auth/otp", json={"role": "expert", "purpose": "signup", "email": "new@example.com",
                                           "phone": "9876543210"})
    assert r.status_code == 409 and "mobile" in r.json()["detail"]
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "signup", "email": "ramesh@example.com",
                                           "phone": "9000000009"})
    assert r.status_code == 409 and "email" in r.json()["detail"]


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
        p = Problem(farm_id=1, target="rice_brown_spot", status="open")
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
