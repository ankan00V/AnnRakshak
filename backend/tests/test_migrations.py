"""The schema changes that only ever run against Postgres.

`init_db` does three things to a database that already exists: adds columns a
newer release expects (ADDED_COLUMNS), widens ones that outgrew their original
size (WIDENED_COLUMNS), and gives older expert profiles their rank and a
designation from the current vocabulary.

Two of those are Postgres-only. SQLite cannot ALTER a column type and does not
enforce a VARCHAR length anyway, so `_widen_columns` returns immediately --
which means the whole widening path was unexercised by a suite that runs on
SQLite. These tests run only when the suite is pointed at a real Postgres
(ANNRAKSHAK_TEST_DB_URL), which CI does.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import inspect, select, text

from app.db import WIDENED_COLUMNS, Base, SessionLocal, _backfill_expert_ranks, engine, init_db
from app.models import Case, ExpertProfile, Farm, Problem, User

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="these migrations are Postgres-only; run with ANNRAKSHAK_TEST_DB_URL to exercise them")


def _width(table: str, column: str) -> int | None:
    col = {c["name"]: c for c in inspect(engine).get_columns(table)}[column]
    return getattr(col["type"], "length", None)


@pytest.fixture()
def fresh():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


def test_a_column_that_outgrew_its_size_is_widened_in_place(fresh):
    """The real round trip: narrow it the way an older release left it, run
    the migration, and the new width is there."""
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE diagnosis ALTER COLUMN model_version TYPE VARCHAR(80)'))
    assert _width("diagnosis", "model_version") == 80

    init_db()

    assert _width("diagnosis", "model_version") == WIDENED_COLUMNS["diagnosis"]["model_version"]


def test_widening_keeps_the_rows_that_are_already_there(fresh):
    """It is an ALTER, not a rebuild. A migration that quietly emptied a table
    would pass a width check and still be a disaster."""
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE "case" ALTER COLUMN reason TYPE VARCHAR(40)'))
    with SessionLocal() as db:
        farm = Farm(farmer_name="Sunita", crop="rice", sowing_date=date.today() - timedelta(days=60),
                    district="Bhandara", lat=21.17, lon=79.65, area_acres=2, is_demo=True)
        db.add(farm)
        db.flush()
        problem = Problem(farm_id=farm.id, status="open")
        db.add(problem)
        db.flush()
        db.add(Case(problem_id=problem.id, status="open", reason="CROP_MISMATCH"))
        db.commit()
        pid = problem.id

    init_db()

    with engine.begin() as conn:
        assert conn.scalar(text("SELECT reason FROM \"case\" WHERE problem_id = :p"), {"p": pid}) == "CROP_MISMATCH"
    assert _width("case", "reason") == WIDENED_COLUMNS["case"]["reason"]


def test_a_second_run_changes_nothing(fresh):
    """init_db runs on every boot, so each step has to be a no-op once done."""
    before = {(t, c): _width(t, c) for t, cols in WIDENED_COLUMNS.items() for c in cols}
    init_db()
    init_db()
    assert {(t, c): _width(t, c) for t, cols in WIDENED_COLUMNS.items() for c in cols} == before


def test_an_older_profile_is_given_its_rank_and_a_current_designation(fresh):
    """The data half, on the database it was written for."""
    with SessionLocal() as db:
        u = User(role="expert", name="Old Row", email="old.pg@kvk.test", is_demo=True)
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
        p = db.get(ExpertProfile, uid)
        assert p.designation == "agri_officer"
        assert p.supervisor is True


def test_the_rank_is_not_handed_back_to_someone_deliberately_demoted(fresh):
    """The backfill runs on every boot, so it must only fire while the database
    has no supervisor at all -- otherwise it would undo a real decision."""
    with SessionLocal() as db:
        for i, (post, sup) in enumerate((("kvk_scientist", True), ("agri_officer", False))):
            u = User(role="expert", name=f"O{i}", email=f"o{i}.pg@kvk.test", is_demo=True)
            db.add(u)
            db.flush()
            db.add(ExpertProfile(user_id=u.id, designation=post, organisation="KVK", employee_id=f"E{i}",
                                 qualification="msc_agri", experience_years=5, districts=["Bhandara"],
                                 crops=["rice"], specialities=[], languages=["mr"],
                                 verified=True, supervisor=sup))
        db.commit()

    _backfill_expert_ranks(engine)

    with SessionLocal() as db:
        demoted = db.scalars(select(ExpertProfile).where(ExpertProfile.designation == "agri_officer")).one()
        assert demoted.supervisor is False, "a deliberate demotion was undone"
