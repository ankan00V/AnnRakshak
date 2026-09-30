"""What the district office can do: issue an advisory, ask for an inspection,
let an officer in, plan the indent, and see what the model cannot name."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import cache, geo, office, services
from app.db import Base, SessionLocal, engine
from app.kb import get_kb
from app.main import app
from app.models import Alert, ExpertProfile, Farm, OfficerAdvisory, User

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
                    db.add(Farm(farmer_name=f"{district}{i}", crop="rice", sowing_date=SOWN,
                                district=district, lat=21.17 + i / 100, lon=79.65, area_acres=2.5,
                                is_demo=True))
            db.add(Farm(farmer_name="Cotton", crop="cotton", sowing_date=SOWN, district="Bhandara",
                        lat=21.2, lon=79.7, area_acres=4, is_demo=True))
            db.commit()
        yield c


def _officer(demo=True, name="Dr. Kale"):
    with SessionLocal() as db:
        u = User(role="expert", name=name, email=f"{name.replace(' ', '')}@kvk.test", is_demo=demo)
        db.add(u)
        db.flush()
        db.add(ExpertProfile(user_id=u.id, designation="kvk_scientist", organisation="KVK",
                             employee_id="E1", qualification="msc_agri", experience_years=5,
                             districts=["Bhandara"], crops=["rice"], specialities=["plant_pathology"],
                             languages=["en"], verified=True))
        db.commit()
        return db.get(User, u.id)


def test_preview_says_who_it_reaches_before_anything_is_sent(client):
    officer = _officer()
    with SessionLocal() as db:
        view = office.preview(db, get_kb(), target="rice_brown_spot", crop="rice",
                              districts=["Bhandara"], kind="advisory", note=None,
                              officer=officer.name, demo=True)
        assert view["farms"] == 3 and view["by_district"] == {"Bhandara": 3}
        assert "Brown spot" in view["reason"]["en"] and officer.name in view["reason"]["en"]
        assert view["reason"]["mr"] != view["reason"]["en"]   # every language, before sending
        assert view["tasks"]["en"]                            # and it carries something to check
        assert db.scalar(select(Alert.id)) is None            # nothing was sent


def test_an_advisory_reaches_that_crop_in_those_districts_only(client):
    officer = _officer()
    with SessionLocal() as db:
        out = office.issue(db, get_kb(), target="rice_brown_spot", crop="rice",
                           districts=["Bhandara"], kind="advisory", level="high",
                           note="Scouts found it in Sakoli.", officer=officer, demo=True)
        assert out["sent"] == 3
        alerts = db.scalars(select(Alert)).all()
        farms = {db.get(Farm, a.farm_id) for a in alerts}
        assert {f.district for f in farms} == {"Bhandara"}
        assert {f.crop for f in farms} == {"rice"}
        assert all(a.trigger == "officer" and a.tasks["en"] for a in alerts)
        assert "Scouts found it in Sakoli." in alerts[0].reason["en"]


def test_issuing_twice_in_a_day_does_not_send_twice(client):
    officer = _officer()
    with SessionLocal() as db:
        kb = get_kb()
        first = office.issue(db, kb, target="rice_brown_spot", crop="rice", districts=[],
                             kind="advisory", level="high", note=None, officer=officer, demo=True)
        second = office.issue(db, kb, target="rice_brown_spot", crop="rice", districts=[],
                              kind="advisory", level="high", note=None, officer=officer, demo=True)
        assert first["sent"] == 5 and second["sent"] == 0 and second["skipped"] == 5


def test_an_inspection_is_worded_as_a_check_not_a_warning(client):
    officer = _officer()
    with SessionLocal() as db:
        office.issue(db, get_kb(), target="rice_brown_spot", crop="rice", districts=["Gondia"],
                     kind="inspection", level="medium", note=None, officer=officer, demo=True)
        alert = db.scalars(select(Alert)).first()
        assert alert.trigger == "inspection"
        assert "checked" in alert.reason["en"]


def test_a_demo_officer_cannot_send_to_a_real_farmer(client):
    officer = _officer()
    with SessionLocal() as db:
        db.add(Farm(farmer_name="Real", crop="rice", sowing_date=SOWN, district="Bhandara",
                    lat=21.17, lon=79.65, area_acres=2, is_demo=False))
        db.commit()
        out = office.issue(db, get_kb(), target="rice_brown_spot", crop="rice", districts=["Bhandara"],
                           kind="advisory", level="high", note=None, officer=officer, demo=True)
        assert out["sent"] == 3  # the real farm is not one of them
        reached = {db.get(Farm, a.farm_id).is_demo for a in db.scalars(select(Alert)).all()}
        assert reached == {True}


def test_the_office_keeps_a_record_of_what_it_sent(client):
    officer = _officer()
    with SessionLocal() as db:
        office.issue(db, get_kb(), target="rice_brown_spot", crop="rice", districts=["Bhandara"],
                     kind="advisory", level="high", note="note", officer=officer, demo=True)
        row = db.scalar(select(OfficerAdvisory))
        assert row.issued_by == officer.id and row.farms == 3 and row.districts == ["Bhandara"]
        assert office.history(db, demo=True)[0]["issued_by"] == officer.name


def test_a_problem_with_no_authored_tasks_cannot_be_broadcast(client):
    """Every alert carries something to check; without that it is just noise."""
    officer = _officer()
    kb = get_kb()
    target = next((t for t in kb.targets if not (kb.rules.get(t, {}).get("tasks") or {}).get("en")), None)
    if target is None:
        pytest.skip("every target has tasks authored")
    with SessionLocal() as db:
        with pytest.raises(ValueError):
            office.issue(db, kb, target=target, crop=kb.targets[target]["crop"], districts=[],
                         kind="advisory", level="high", note=None, officer=officer, demo=True)


def test_an_officer_reviews_nothing_until_the_office_says_so(client):
    with SessionLocal() as db:
        u = User(role="expert", name="New Joiner", email="new@kvk.test", is_demo=True)
        db.add(u)
        db.flush()
        db.add(ExpertProfile(user_id=u.id, designation="agriculture_officer", organisation="DAO",
                             employee_id="E9", qualification="bsc_agri", experience_years=2,
                             districts=["Bhandara"], crops=["rice"], specialities=[], languages=["mr"],
                             verified=False))
        db.commit()
        uid = u.id
        assert [o["user_id"] for o in office.pending_officers(db, demo=True)] == [uid]
        # Unverified: the router will not hand them a case.
        assert all(c.user_id != uid for c in services.officers_for(db, "Bhandara", demo=True))
        office.set_verified(db, uid, True)
        assert office.pending_officers(db, demo=True) == []
        assert any(c.user_id == uid for c in services.officers_for(db, "Bhandara", demo=True))


def test_the_indent_plan_counts_farms_and_acres_and_names_the_lead_time(client):
    officer = _officer()
    with SessionLocal() as db:
        kb = get_kb()
        office.issue(db, kb, target="rice_leaf_folder", crop="rice", districts=[],
                     kind="advisory", level="high", note=None, officer=officer, demo=True)
        rows = office.indent(db, kb, demo=True)
        row = next(r for r in rows if r["target"] == "rice_leaf_folder")
        assert row["farms"] == 5 and row["acres"] == 12.5
        assert sorted(row["districts"]) == ["Bhandara", "Gondia"]
        tricho = [s for s in row["suggested"] if "tricho" in s["input"].lower()]
        if tricho:   # the ICAR repository entry for leaf folder is a Tricho-card
            assert tricho[0]["order_by"] == (date.today() + timedelta(days=45)).isoformat()
        csv_text = office.indent_csv(rows)
        assert "Problem,Crop,Farms" in csv_text and "Rice leaf folder" in csv_text


def test_everything_the_indent_hands_the_screen_is_printable(client):
    """An institute is a record in the knowledge base, not a name — handing the
    object straight to the page blanked the whole console once."""
    officer = _officer()
    with SessionLocal() as db:
        kb = get_kb()
        office.issue(db, kb, target="rice_leaf_folder", crop="rice", districts=[],
                     kind="advisory", level="high", note=None, officer=officer, demo=True)
        for row in office.indent(db, kb, demo=True):
            for s in row["suggested"]:
                assert isinstance(s["input"], str)
                assert s["institute"] is None or isinstance(s["institute"], str)
                assert isinstance(s["quantity"], str)


def test_the_worklist_puts_the_longest_wait_first(client):
    """Cases past the 24-hour mark, oldest first — that is the queue that matters."""
    from app.models import Case, Problem
    with SessionLocal() as db:
        ids = []
        for hours in (3, 40, 70):
            p = Problem(farm_id=1, status="open")
            db.add(p)
            db.flush()
            c = Case(problem_id=p.id, status="open", reason="BELOW_FLOOR",
                     created_at=date.today() and __import__("datetime").datetime.now() - timedelta(hours=hours))
            db.add(c)
            db.flush()
            ids.append((hours, c.id))
        db.commit()
        work = office.worklist(db, get_kb(), demo=True)
    assert work["overdue_count"] == 2
    assert [r["id"] for r in work["overdue_cases"]] == [ids[2][1], ids[1][1]]
    assert work["sla_hours"] == 24
    assert len(work["unrouted"]) == 3    # nobody verified covers them yet
