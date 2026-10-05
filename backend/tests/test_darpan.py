"""Darpan answers an officer about their district, from the district's own rows.

Krishi is the farmers' helper and is not touched by any of this.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import cache, darpan, geo, office
from app.db import Base, SessionLocal, engine
from app.kb import get_kb
from app.main import app
from app.models import Alert, Case, ExpertProfile, Farm, Problem, User

SOWN = date.today() - timedelta(days=60)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(geo, "locate", lambda state, district, village=None: {"lat": 21.17, "lon": 79.65})
    cache._counts.clear()
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:
        with SessionLocal() as db:
            for district, n in (("Bhandara", 3), ("Gondia", 2)):
                for i in range(n):
                    db.add(Farm(farmer_name=f"Sunita {district}{i}", crop="rice", sowing_date=SOWN,
                                district=district, lat=21.17, lon=79.65, area_acres=2, is_demo=True,
                                village="Sakoli"))
            db.commit()
        yield c


def _officer(demo=True):
    """The signed-in officer; made once and reused, like a real account."""
    with SessionLocal() as db:
        found = db.scalar(select(User).where(User.email == "kale@kvk.test"))
        if found:
            return found
        u = User(role="expert", name="Dr. Kale", email="kale@kvk.test", is_demo=demo)
        db.add(u)
        db.flush()
        db.add(ExpertProfile(user_id=u.id, designation="kvk_scientist", organisation="KVK",
                             employee_id="E1", qualification="phd", experience_years=9,
                             districts=["Bhandara"], crops=["rice"], specialities=[], languages=["en"],
                             verified=True, supervisor=True))
        db.commit()
        return db.get(User, u.id)


def _case(district="Bhandara", hours_old=2):
    with SessionLocal() as db:
        farm = db.scalar(select(Farm).where(Farm.district == district))
        p = Problem(farm_id=farm.id, status="open")
        db.add(p)
        db.flush()
        db.add(Case(problem_id=p.id, status="open", reason="BELOW_FLOOR",
                    created_at=datetime.now() - timedelta(hours=hours_old)))
        db.commit()


def ask(text, demo=True):
    with SessionLocal() as db:
        return darpan.answer(db, get_kb(), text=text, demo=demo, officer=_officer())


def test_it_answers_the_queue_from_the_real_rows(client):
    _case(hours_old=2)
    _case(hours_old=40)
    out = ask("how is the queue")
    assert out["intent"] == "queue"
    assert "2 open cases" in out["lines"][0]
    assert "1 past the 24-hour mark" in " ".join(out["lines"])
    assert any(g["to"] == "/officer/queue?overdue=1" for g in out["go"])


def test_a_district_by_name_is_understood(client):
    _case("Bhandara")
    out = ask("how is bhandara doing")
    assert out["intent"] == "district"
    assert out["lines"][0].startswith("Bhandara: 3 farms monitored, 1 case open")
    assert any("Bhandara" in g["to"] for g in out["go"])


def test_it_says_what_is_building_and_offers_the_advisory(client):
    with SessionLocal() as db:
        farm = db.scalar(select(Farm))
        db.add(Alert(farm_id=farm.id, target="rice_brown_spot", trigger="weather", level="high",
                     reason={"en": "x"}, tasks={"en": ["look"]}, issued_on=date.today()))
        db.commit()
    out = ask("what is building this week")
    assert out["intent"] == "building"
    assert any("Brown spot" in line for line in out["lines"])
    assert any("advisories?target=rice_brown_spot" in g["to"] for g in out["go"])


def test_it_says_who_is_carrying_what(client):
    """The intent that shipped broken because no test asked it anything."""
    _case()
    out = ask("who is free")
    assert out["intent"] == "officers"
    assert out["lines"]
    assert any(g["to"] == "/officer/officers" for g in out["go"])


def test_every_intent_answers_without_falling_over(client):
    """One question per intent, so a wrong module name cannot ship again."""
    _case()
    for question, expected in [
        ("how is the queue", "queue"),
        ("how is bhandara doing", "district"),
        ("what is building", "building"),
        ("advisories issued", "advisories"),
        ("who has the most cases", "officers"),
        ("how accurate is the model", "model"),
        ("what can the model not name", "gaps"),
        ("what should i order", "inputs"),
        ("how is the rain", "rainfall"),
        ("find sunita", "farm"),
        ("what can you do", "help"),
    ]:
        out = ask(question)
        assert out["intent"] == expected, (question, out["intent"])
        assert out["lines"] and all(isinstance(line, str) for line in out["lines"])
        assert all({"label", "to"} <= set(g) for g in out["go"])


def test_it_reports_whether_an_advisory_was_acted_on(client):
    officer = _officer()
    with SessionLocal() as db:
        office.issue(db, get_kb(), target="rice_brown_spot", crop="rice", districts=["Bhandara"],
                     kind="advisory", level="high", note=None, officer=officer, demo=True)
        db.commit()
    out = ask("did anyone check the advisory")
    assert out["intent"] == "advisories"
    assert "nobody has checked yet" in " ".join(out["lines"])


def test_it_finds_a_farmer_and_links_to_the_field(client):
    out = ask("find sunita")
    assert out["intent"] == "farm"
    assert any(g["to"].startswith("/officer/farm/") for g in out["go"])


def test_it_refuses_what_it_cannot_answer_instead_of_guessing(client, monkeypatch):
    monkeypatch.setattr(darpan.llm, "enabled", lambda: False)
    out = ask("what is the price of urea in nagpur")
    assert out["intent"] == "unknown"
    assert "only answer from this district's own records" in out["lines"][0]


def test_darpan_is_for_officers_only(client, monkeypatch):
    """A farmer never reaches it, signed in or not. (Krishi stays theirs.)"""
    from app import config
    monkeypatch.setattr(config, "AUTH_ENFORCE", True)
    assert client.get("/api/darpan/hello").status_code in (401, 403)
    assert client.post("/api/darpan/ask", json={"text": "how is the queue"}).status_code in (401, 403)
    assert client.get("/api/krishi/hello").status_code == 200   # the farmers' helper is untouched


def test_demo_and_real_districts_are_answered_separately(client):
    _case("Bhandara")
    with SessionLocal() as db:                       # a real farm with its own case
        farm = Farm(farmer_name="Real", crop="rice", sowing_date=SOWN, district="Latur",
                    lat=18.4, lon=76.5, area_acres=2, is_demo=False)
        db.add(farm)
        db.flush()
        p = Problem(farm_id=farm.id, status="open")
        db.add(p)
        db.flush()
        db.add(Case(problem_id=p.id, status="open", reason="BELOW_FLOOR", created_at=datetime.now()))
        db.commit()
    assert "1 open case" in ask("how is the queue", demo=True)["lines"][0]
    assert "1 open case" in ask("how is the queue", demo=False)["lines"][0]
