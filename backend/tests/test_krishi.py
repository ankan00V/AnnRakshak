"""Krishi, the in-app helper: finds the right answer for how farmers actually
ask (English, Hindi, Marathi, and romanised Hinglish / Minglish), answers
from the farm's own data where the question is about today, and says so
instead of guessing when a question is outside the app."""

import pytest

from app import config, krishi
from app.engine import agroweather
from app.i18n import LANGS
from app.models import Alert, Problem
from sqlalchemy import select
from app.db import SessionLocal
from tests.test_weather import NOW, bundle, humid, storm, world  # noqa: F401  (fixture)

# (question, screen the farmer is on, topic Krishi must pick; None = "I didn't understand")
CASES = [
    ("can i spray today", "weather", "spray_now"),
    ("spray kab karu", None, "spray_now"),
    ("फवारणी कधी करू", None, "spray_now"),
    ("क्या आज दवा छिड़क सकते हैं", None, "spray_now"),
    ("will it rain tomorrow", None, "weather_now"),
    ("aaj barish hogi kya", None, "weather_now"),
    ("पाऊस कधी येणार", None, "weather_now"),
    ("should i give water to my crop", None, "irrigate_now"),
    ("पाणी कधी द्यायचे", None, "irrigate_now"),
    ("how to check disease on leaf", None, "scan_photo"),
    ("पत्तों पर पीले धब्बे हैं क्या करूँ", None, "scan_photo"),
    ("पानांवर ठिपके आले आहेत", None, "scan_photo"),
    ("which medicine to spray for blast", None, "which_pesticide"),
    ("कौन सी दवा डालूँ", None, "which_pesticide"),
    ("how do i change language", None, "language"),
    ("bhasha kaise badle", None, "language"),
    ("what did the expert say", None, "my_cases"),
    ("expert ka jawab aaya kya", None, "my_cases"),
    ("how to add another farm", None, "switch_farm"),
    ("दुसरे शेत जोडायचे आहे", None, "switch_farm"),
    ("what is the bell icon", None, "notices"),
    ("how to get notifications on phone", None, "notifications"),
    ("where do i enter trap count", None, "traps"),
    ("what does 80% sure mean", "result", "confidence"),
    ("why is it asking me question", "result", "doubt_question"),
    ("how long will expert take", "result", "expert_wait"),
    ("why chemical hidden", "result", "advice_ladder"),
    ("is this pesticide safe", "spray", "never_safe"),
    ("check my pesticide bottle", None, "spray_check"),
    ("video call", None, "live_check"),
    ("कापूस पिकासाठी चालते का", None, "crop_support"),
    ("i didn't get the otp", "login", "no_code"),
    ("code nahi aaya", "login", "no_code"),
    ("why email not sms", "signup", "signup_email"),
    ("i am agriculture officer which account", "signup", "signup_role"),
    ("what is soil health card", None, "soil_card"),
    ("कौन सा रोग आ सकता है", None, "risks_now"),
    ("आज काय करायचे", None, "today"),
    ("how old is my crop", None, "my_farm"),
    ("who can see my data", None, "privacy"),
    ("app not opening no internet", None, "offline"),
    ("urea kitna dalna", None, "fertilizer"),
    ("what is the price of onion in market", None, "not_app"),
    ("namaste", None, "greeting"),
    ("asdf qwerty", None, None),
]


def test_knowledge_base_is_complete():
    assert krishi.validate(krishi.load()) == []


@pytest.mark.parametrize(("question", "screen", "want"), CASES)
def test_finds_the_right_topic(question, screen, want):
    ranked = krishi.index().rank(question, screen)
    got = ranked[0][0] if ranked and ranked[0][1] >= krishi.MATCH_MIN else None
    assert got == want, ranked[:3]


@pytest.fixture()
def krishi_world(world, monkeypatch):  # noqa: F811
    c, _ = world
    monkeypatch.setattr(agroweather, "now_ist", lambda: NOW)
    return c


def test_hello_offers_questions_for_the_screen(krishi_world):
    c = krishi_world
    h = c.get("/api/krishi/hello?lang=mr&screen=weather").json()
    assert h["text"].startswith("नमस्कार") and [s["id"] for s in h["suggestions"]][:2] == ["spray_now", "irrigate_now"]
    for lang in LANGS:  # every language has its greeting and chips
        h = c.get(f"/api/krishi/hello?lang={lang}&screen=home").json()
        assert h["text"] and len(h["suggestions"]) == 4 and all(s["text"] for s in h["suggestions"])


def test_authored_answer_with_a_button(krishi_world):
    r = krishi_world.post("/api/krishi/ask", json={"text": "how do I check a sick plant", "lang": "hi",
                                                   "screen": "home"}).json()
    assert r["topic"] == "scan_photo" and "जाँच" in r["text"] and r["go"] == [{"to": "/app/scan", "label": "जाँच खोलें"}]
    assert r["suggestions"] and all(s["id"] != "scan_photo" for s in r["suggestions"])


def test_chip_tap_answers_that_topic(krishi_world):
    r = krishi_world.post("/api/krishi/ask", json={"topic": "photo_tips", "lang": "en"}).json()
    assert r["topic"] == "photo_tips" and len(r["steps"]) == 4


def test_spray_now_answers_from_the_forecast(krishi_world, monkeypatch):
    b = bundle(hour=lambda t, row: (storm(t, row), humid(t, row)))
    monkeypatch.setattr(agroweather, "bundle", lambda lat, lon: b)
    r = krishi_world.post("/api/krishi/ask", json={"text": "can I spray now", "lang": "en", "farm_id": 1}).json()
    assert r["topic"] == "spray_now" and r["text"].startswith(("No", "You can", "Yes"))
    assert any("Spray check" in s for s in r["steps"]) and r["go"][0]["to"] == "/app/weather"


def test_weather_and_today_from_the_farm(krishi_world, monkeypatch):
    b = bundle(hour=humid)
    monkeypatch.setattr(agroweather, "bundle", lambda lat, lon: b)
    c = krishi_world
    with SessionLocal() as db:
        db.add(Alert(farm_id=1, target="rice_blast", trigger="weather", level="high", reason={"en": "x"},
                     tasks={"en": ["Look at 10 leaves for eye-shaped spots"]}, issued_on=NOW.date()))
        db.commit()
    w = c.post("/api/krishi/ask", json={"text": "will it rain", "lang": "mr", "farm_id": 1}).json()
    assert w["topic"] == "weather_now" and "°C" in w["text"] and "आर्द्रता" in w["text"]
    t = c.post("/api/krishi/ask", json={"topic": "today", "lang": "en", "farm_id": 1}).json()
    assert t["text"].startswith("Today for your Rice") and any("eye-shaped" in s for s in t["steps"])


def test_cases_and_farm_answers(krishi_world):
    c = krishi_world
    none = c.post("/api/krishi/ask", json={"topic": "my_cases", "lang": "en", "farm_id": 1}).json()
    assert "haven't reported" in none["text"]
    with SessionLocal() as db:
        db.add(Problem(farm_id=1, target="rice_blast", status="open"))
        db.commit()
    some = c.post("/api/krishi/ask", json={"topic": "my_cases", "lang": "en", "farm_id": 1}).json()
    assert some["steps"] and "Rice blast" in some["steps"][0]
    f = c.post("/api/krishi/ask", json={"topic": "my_farm", "lang": "en", "farm_id": 1}).json()
    assert "days old" in f["text"] and "Bhandara" in f["text"] and "Rice" in f["text"]


def test_live_answer_needs_a_farm_the_caller_may_open(krishi_world, monkeypatch):
    c = krishi_world
    r = c.post("/api/krishi/ask", json={"topic": "spray_now", "lang": "en"}).json()
    assert "Open one of your fields" in r["text"]
    monkeypatch.setattr(config, "AUTH_ENFORCE", True)  # signed out: farm 1 is not theirs
    r = c.post("/api/krishi/ask", json={"topic": "my_farm", "lang": "en", "farm_id": 1}).json()
    assert "Open one of your fields" in r["text"] and "Bhandara" not in r["text"]


def test_says_so_instead_of_guessing(krishi_world):
    r = krishi_world.post("/api/krishi/ask", json={"text": "asdf qwerty", "lang": "en", "screen": "spray"}).json()
    assert r["topic"] is None and "1800-180-1551" in r["text"] and r["suggestions"][0]["id"] == "spray_check"


def test_never_names_a_pesticide():
    """Authored answers point to the photo check and Spray check; none recommends a product."""
    import re

    products = re.compile(r"mancozeb|tricyclazole|imidacloprid|chlorpyrifos|carbendazim|propiconazole", re.I)
    for t in krishi.load()["topics"]:
        for lang, text in t.get("answer", {}).items():
            if t["id"] != "spray_check":  # 'for example Mancozeb' shows what to type, not what to buy
                assert not products.search(text), (t["id"], lang)


# --------------------------------------------------------------------------
# Krishi as a personal assistant: the farmer's own details, and only theirs
# --------------------------------------------------------------------------

def test_a_number_that_is_not_in_the_farmer_s_own_rows_is_refused():
    sheet = "Field 1: Rice, 3.0 acres, sown 01 Jul 2026, 80 days ago."
    assert krishi.grounded("You have 3.0 acres of rice, sown 80 days ago.", sheet)
    assert krishi.grounded("You have 3 acres of rice.", sheet)         # same number, said plainly
    assert krishi.grounded("Sown on 1 July 2026.", sheet)              # "1" for "01"
    assert not krishi.grounded("You have 5 acres of rice.", sheet)     # invented area
    assert not krishi.grounded("It was sown 45 days ago.", sheet)      # invented age
    assert krishi.grounded("Your rice is doing well.", sheet)          # no numbers to check


def test_the_facts_sheet_holds_only_the_signed_in_farmer_s_fields(monkeypatch):
    """The boundary that matters: Krishi builds its answer from the rows of the
    user it was handed, so another farmer's field cannot appear in it."""
    from datetime import timedelta

    from app.db import Base, SessionLocal, engine
    from app.kb import get_kb
    from app.models import Farm, FarmerProfile, User

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        mine = User(name="Sunita", role="farmer", email="sunita@example.com", phone="9800000001")
        theirs = User(name="Ramesh", role="farmer", email="ramesh@example.com", phone="9800000002")
        db.add_all([mine, theirs])
        db.flush()
        db.add_all([
            FarmerProfile(user_id=mine.id, district="Bhandara", village="Pauni",
                          consent_at=NOW, total_land_acres=3),
            Farm(user_id=mine.id, farmer_name="Sunita", crop="rice", sowing_date=NOW.date() - timedelta(days=80),
                 district="Bhandara", village="Pauni", lat=21.17, lon=79.65, area_acres=2, lang="mr"),
            Farm(user_id=theirs.id, farmer_name="Ramesh", crop="cotton", sowing_date=NOW.date() - timedelta(days=40),
                 district="Yavatmal", village="Ner", lat=20.4, lon=78.1, area_acres=9, lang="mr"),
        ])
        db.commit()
        mine_farms = list(db.scalars(select(Farm).where(Farm.user_id == mine.id)).all())
        sheet = krishi.facts(db, get_kb(), db.get(User, mine.id), mine_farms, "en")

    assert "Sunita" in sheet and "Pauni" in sheet and "2.0 acres" in sheet
    for leak in ("Ramesh", "Yavatmal", "Ner", "9.0 acres", "ramesh@example.com", "9800000002"):
        assert leak not in sheet, f"another farmer's {leak} reached the answer"


def test_no_personal_answer_without_a_signed_in_farmer():
    from app.kb import get_kb
    from app.db import SessionLocal

    with SessionLocal() as db:
        assert krishi.facts(db, get_kb(), None, [], "en") == ""
        assert krishi._personal(db, get_kb(), None, [], "how much land do I have", "en", "home") is None
