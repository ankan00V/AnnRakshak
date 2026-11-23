"""Krishi and Darpan as assistants (app.assistant), with the model scripted.

The model is replaced by a list of replies, so each test says exactly what the
model "decided" and checks what the app did with it: which lookups ran, what
reached the farmer, and what was thrown away.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import assistant, darpan, geo, krishi, llm
from app.db import Base, SessionLocal, engine
from app.kb import get_kb
from app.main import app
from app.models import Farm, User

kb = get_kb()


def call(name: str, **args) -> dict:
    return {"id": f"c_{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


@pytest.fixture()
def scripted(monkeypatch):
    """Replace the model with replies given in order; record what it was sent."""
    replies: list[dict] = []
    sent: list[list[dict]] = []

    def chat_tools(messages, tools, **_):
        sent.append([dict(m) for m in messages])
        return replies.pop(0) if replies else None

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "chat_tools", chat_tools)
    monkeypatch.setattr(llm, "route", lambda *a, **k: None)
    monkeypatch.setattr(llm, "restyle", lambda *a, **k: None)
    return replies, sent


@pytest.fixture()
def world(monkeypatch):
    monkeypatch.setattr(geo, "locate", lambda state, district, village=None: {"lat": 21.17, "lon": 79.65})
    Base.metadata.drop_all(bind=engine)
    with TestClient(app):
        with SessionLocal() as db:
            me = User(role="farmer", name="Asha", phone="+919800000001")
            other = User(role="farmer", name="Someone else", phone="+919800000002")
            db.add_all([me, other])
            db.flush()
            db.add(Farm(user_id=me.id, farmer_name="Asha", crop="maize", sowing_date=date.today() - timedelta(days=30),
                        district="Pune", lat=18.5, lon=73.8, area_acres=3))
            db.add(Farm(user_id=other.id, farmer_name="Other", crop="rice", sowing_date=date.today() - timedelta(days=30),
                        district="Bhandara", lat=21.1, lon=79.6, area_acres=9))
            db.commit()
        yield


def mine(db):
    user = db.query(User).filter_by(name="Asha").one()
    farms = db.query(Farm).filter_by(user_id=user.id).all()
    return user, farms


def test_the_assistant_looks_things_up_and_shows_the_spray_advice_as_the_app_gives_it(world, scripted, monkeypatch):
    replies, _ = scripted
    monkeypatch.setattr(krishi, "_spray", lambda db, kb, farm, lang: {
        "text": "No — don't spray now: rain expected. Next good time: tomorrow 07:00–10:00.", "steps": [],
        "go": [{"to": "/app/weather", "label": "Open Weather"}]})
    monkeypatch.setattr(krishi, "_risks", lambda db, kb, farm, lang: {
        "text": "The weather and your crop's growth stage favour these now:", "steps": ["Fall armyworm: risk"], "go": []})
    replies += [{"content": "", "tool_calls": [call("spray_window"), call("pest_risks")]},
                {"content": json.dumps({"text": "Fall armyworm is the risk now.",
                                        "points": ["Watch the whorls for fresh damage"]})}]
    with SessionLocal() as db:
        user, farms = mine(db)
        out = krishi.answer(db, kb, text="can i spray today and what for?", topic=None, screen="home", lang="en",
                            farm=farms[0], user=user, farms=farms)
    assert out["topic"] == "assistant" and out["used"] == ["spray_window", "pest_risks"]
    assert out["steps"][0].startswith("No — don't spray now")  # word for word, first
    assert {"to": "/app/weather", "label": "Open Weather"} in out["go"]


def test_an_answer_with_a_number_no_lookup_gave_is_thrown_away(world, scripted):
    replies, _ = scripted
    replies += [{"content": "", "tool_calls": [call("app_help", question="how do i take a photo")]},
                {"content": json.dumps({"text": "Spray 2.5 ml per litre today.", "points": []})}]
    with SessionLocal() as db:
        user, farms = mine(db)
        out = krishi.answer(db, kb, text="what should i do with my field and the photo?", topic=None, screen="home",
                            lang="en", farm=farms[0], user=user, farms=farms)
    assert out["topic"] != "assistant"  # the fixed answer stood
    assert "2.5" not in out["text"]


def test_an_answer_naming_a_pesticide_no_lookup_returned_is_thrown_away():
    evidence = "Fall armyworm: risk. Beauveria bassiana 1.5% AS, 6.3 ml per litre."
    assert assistant.grounded(kb, "Use Beauveria bassiana 1.5% AS at 6.3 ml per litre.", evidence)
    assert not assistant.grounded(kb, "Use emamectin benzoate at 6.3 ml per litre.", evidence)
    assert not assistant.grounded(kb, "Use Beauveria at 9 ml per litre.", evidence)


def test_no_model_means_the_fixed_answer(world, scripted):
    replies, sent = scripted  # no replies: the model "fails"
    with SessionLocal() as db:
        user, farms = mine(db)
        out = krishi.answer(db, kb, text="what is the weather and should i water?", topic=None, screen="home",
                            lang="en", farm=farms[0], user=user, farms=farms)
    assert sent and out["topic"] != "assistant"


def test_a_farmers_lookups_never_reach_another_farmers_field(world, scripted, monkeypatch):
    seen = []
    monkeypatch.setattr(krishi, "_weather", lambda db, kb, farm, lang: (seen.append(farm.id), {"text": "ok"})[1])
    replies, _ = scripted
    replies += [{"content": "", "tool_calls": [call("weather", field_no=2), call("weather", field_no=99)]},
                {"content": json.dumps({"text": "ok", "points": []})}]
    with SessionLocal() as db:
        user, farms = mine(db)
        krishi.answer(db, kb, text="weather at my other field and the second one?", topic=None, screen="home",
                      lang="en", farm=farms[0], user=user, farms=farms)
        other = db.query(Farm).filter_by(farmer_name="Other").one()
    assert seen and other.id not in seen and set(seen) == {farms[0].id}


def test_a_question_the_app_knows_does_not_wait_for_the_model(world, scripted):
    _, sent = scripted
    with SessionLocal() as db:
        user, farms = mine(db)
        out = krishi.answer(db, kb, text="how do I take a photo of a sick plant", topic=None, screen="home",
                            lang="en", farm=farms[0], user=user, farms=farms)
    assert not sent and out["topic"] in ("scan_photo", "photo_tips")


def test_a_price_question_goes_to_the_assistant_not_the_crops_answer(world, scripted):
    replies, sent = scripted
    replies += [{"content": json.dumps({"text": "I can't help with mandi prices. The Kisan Call Centre on "
                                                "1800-180-1551 is free.", "points": []})}]
    with SessionLocal() as db:
        user, farms = mine(db)
        out = krishi.answer(db, kb, text="what is the price of cotton in the mandi?", topic=None, screen="home",
                            lang="en", farm=farms[0], user=user, farms=farms)
    assert sent and out["topic"] == "assistant" and "1800-180-1551" in out["text"]


def test_darpan_answers_a_two_part_question_from_two_lookups(world, scripted):
    replies, _ = scripted
    replies += [{"content": "", "tool_calls": [call("brief"), call("stock")]},
                {"content": json.dumps({"lines": ["0 cases open, none overdue.", "Nothing to order."]})}]
    with SessionLocal() as db:
        out = darpan.answer(db, kb, text="brief me and tell me what to stock", demo=False, officer=None)
    assert out["intent"] == "assistant" and out["used"] == ["brief", "stock"]
    assert out["lines"] == ["0 cases open, none overdue.", "Nothing to order."]


def test_darpan_keeps_its_fixed_answer_when_the_assistant_invents(world, scripted):
    replies, _ = scripted
    replies += [{"content": "", "tool_calls": [call("brief")]},
                {"content": json.dumps({"lines": ["17 cases are overdue in Gondia."]})}]
    with SessionLocal() as db:
        out = darpan.answer(db, kb, text="brief me and how is the queue?", demo=False, officer=None)
    assert out["intent"] != "assistant" and "17" not in " ".join(out["lines"])


def test_any_talk_of_spraying_leads_with_the_apps_own_spray_window(world, scripted, monkeypatch):
    """The model read a time off another lookup and said "spray today 13:00–18:00"
    when the spray window said not now. Whatever it says about spraying is
    replaced by the window's own sentence."""
    monkeypatch.setattr(krishi, "_spray", lambda db, kb, farm, lang: {
        "text": "No — don't spray now: too windy. Next good time: tomorrow 13:00–18:00.", "steps": [], "go": []})
    monkeypatch.setattr(krishi, "_today", lambda db, kb, farm, lang: {"text": "Window 13:00–18:00", "steps": []})
    replies, _ = scripted
    replies += [{"content": "", "tool_calls": [call("field_today")]},
                {"content": json.dumps({"text": "Spray today 13:00–18:00.", "points": ["Spray 13:00–18:00", "All calm"]})}]
    with SessionLocal() as db:
        user, farms = mine(db)
        out = krishi.answer(db, kb, text="what should i do today and is the weather ok?", topic=None, screen="home",
                            lang="en", farm=farms[0], user=user, farms=farms)
    said = " ".join([out["text"], *out["steps"]])
    assert out["text"].startswith("No — don't spray now")
    assert "Spray today" not in said and "Spray 13:00" not in said and "All calm" in said


def test_a_final_answer_sent_as_a_fake_tool_call_is_recovered_and_no_key_is_benched(monkeypatch):
    """gpt-oss sometimes "calls" a tool named JSON with its answer. Groq refuses
    that with a 400 that carries the generation; the answer is taken from it,
    and the key is not benched — benching on it once sat all twelve keys out."""
    import httpx

    class Refusal:
        status_code = 400
        text = "refused"

        def json(self):
            return {"error": {"code": "tool_use_failed", "message": "attempted to call tool 'JSON'",
                              "failed_generation": json.dumps({"name": "JSON", "arguments": {"lines": ["ok"]}})}}

    calls = []
    monkeypatch.setattr(llm, "GROQ_API_KEYS", ["k1", "k2"])
    monkeypatch.setattr(llm, "_benched", {})
    monkeypatch.setattr(httpx, "post", lambda *a, **k: (calls.append(1), Refusal())[1])
    tools = [{"type": "function", "function": {"name": "brief", "parameters": {"type": "object", "properties": {}}}}]
    msg = llm.chat_tools([{"role": "user", "content": "q"}], tools)
    assert json.loads(msg["content"]) == {"lines": ["ok"]}
    assert calls == [1] and llm._benched == {}


# --- demo accounts ---------------------------------------------------------------

def _client_as(monkeypatch, user):
    from app import auth
    from app.routers import darpan as darpan_router
    monkeypatch.setattr(auth, "current_user", lambda request, db: user)
    for dep in darpan_router.router.dependencies:
        app.dependency_overrides[dep.dependency] = lambda: None
    return TestClient(app)


def test_a_demo_farmer_is_greeted_and_sent_to_register_whatever_they_ask(world, scripted, monkeypatch):
    replies, sent = scripted
    demo = User(id=999, role="farmer", name="Demo farmer", is_demo=True)
    try:
        with _client_as(monkeypatch, demo) as c:
            out = c.post("/api/krishi/ask", json={"text": "how do i control stem borer", "lang": "en"}).json()
            hi = c.post("/api/krishi/ask", json={"text": "धान में तना छेदक", "lang": "hi"}).json()
            chip = c.post("/api/krishi/ask", json={"topic": "live_check", "lang": "en"}).json()
            hello = c.get("/api/krishi/hello?lang=en&screen=home").json()
    finally:
        app.dependency_overrides.clear()
    assert out["topic"] == "demo" and "demo account" in out["text"] and out["go"][0]["to"] == "/signup/farmer"
    assert hi["lang"] == "hi" and "डेमो" in hi["text"]
    assert chip["topic"] == "demo"  # a tapped question too
    assert "demo account" in hello["text"] and hello["suggestions"] == []  # nothing to tap from the start
    assert not sent  # no lookup, no model call for a demo


def test_a_demo_officer_gets_a_greeting_from_darpan_not_district_numbers(world, scripted, monkeypatch):
    demo = User(id=998, role="expert", name="Demo expert", is_demo=True)
    try:
        with _client_as(monkeypatch, demo) as c:
            out = c.post("/api/darpan/ask", json={"text": "brief me"}).json()
            hello = c.get("/api/darpan/hello").json()
    finally:
        app.dependency_overrides.clear()
    assert out["intent"] == "demo" and out["go"] == [{"label": "Register as an officer", "to": "/signup/expert"}]
    assert out["lines"][0].startswith("Namaste! This is a demo account")
    assert hello["greeting"].startswith("Namaste! This is a demo account") and hello["suggestions"] == []
