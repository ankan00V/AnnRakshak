"""One open question per problem.

A problem can be advised more than once — a second opinion, a re-decide after
a new model ships, the same photograph sent twice — and each advice used to
add its own follow-up. They came due on the same day and asked the same
question about the same disease, so the home screen stacked identical cards
and answering one left the others sitting there. Found on the demonstration
rice field, which had two for problem 121 and five in all.

`escalate()` had guarded against exactly this for cases since it was written.
Scheduling a follow-up had not.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app import services
from app.db import Base, SessionLocal, engine
from app.models import FollowUp, Farm, Problem

SOWN = date.today() - timedelta(days=60)


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as s:
        yield s


def _problem(db) -> Problem:
    farm = Farm(farmer_name="Sunita", crop="rice", sowing_date=SOWN, district="Bhandara",
                lat=21.17, lon=79.65, area_acres=2, is_demo=True)
    db.add(farm)
    db.flush()
    problem = Problem(farm_id=farm.id, status="open", target="rice_blast")
    db.add(problem)
    db.flush()
    return problem


def _open_followups(db, problem) -> list[FollowUp]:
    return list(db.scalars(
        select(FollowUp).where(FollowUp.problem_id == problem.id, FollowUp.response.is_(None))
    ))


def test_advising_the_same_problem_twice_asks_one_question(db):
    problem = _problem(db)

    first = services._schedule_followup(db, problem)
    second = services._schedule_followup(db, problem)

    assert first.id == second.id
    assert len(_open_followups(db, problem)) == 1


def test_an_answered_follow_up_does_not_block_the_next_round(db):
    """What `respond_followup` relies on when the answer is "the same".

    The response is set before the next one is asked for, so the open-question
    guard has to be about open questions, not about any question ever asked.
    """
    problem = _problem(db)
    first = services._schedule_followup(db, problem)
    first.response = "same"
    db.flush()

    second = services._schedule_followup(db, problem)

    assert second.id != first.id
    assert len(_open_followups(db, problem)) == 1


def test_two_problems_on_one_farm_each_keep_their_own_question(db):
    """The guard is per problem, not per farm — two diseases, two questions."""
    one = _problem(db)
    two = Problem(farm_id=one.farm_id, status="open", target="rice_brown_spot")
    db.add(two)
    db.flush()

    a = services._schedule_followup(db, one)
    b = services._schedule_followup(db, two)

    assert a.id != b.id
    assert len(_open_followups(db, one)) == 1
    assert len(_open_followups(db, two)) == 1


def test_the_question_that_is_kept_is_the_one_already_due(db):
    """Returning the existing row keeps its due date.

    Handing back a later date each time something re-advised would walk the
    question into the future and it would never be asked.
    """
    problem = _problem(db)
    first = services._schedule_followup(db, problem, today=date(2026, 1, 1))

    again = services._schedule_followup(db, problem, today=date(2026, 6, 1))

    assert again.id == first.id
    assert again.due_on == first.due_on


def test_the_duplicates_the_old_behaviour_left_are_cleared_on_boot(db):
    """`db._dedupe_open_followups`, against the shape really found.

    Problem 121 on the demonstration rice field had two unanswered follow-ups
    and problem 67 on another farm had two more. The earliest survives, since
    it carries the due date the farmer was promised.
    """
    from app import db as dbmod

    problem = _problem(db)
    keep = FollowUp(problem_id=problem.id, due_on=date(2026, 10, 28))
    dupe = FollowUp(problem_id=problem.id, due_on=date(2026, 11, 4))
    answered = FollowUp(problem_id=problem.id, due_on=date(2026, 10, 1), response="same")
    db.add_all([answered, keep, dupe])
    db.commit()

    dbmod._dedupe_open_followups(db.get_bind())
    db.expire_all()

    left = _open_followups(db, problem)
    assert [f.id for f in left] == [keep.id]
    assert left[0].due_on == date(2026, 10, 28)
    # The record of what was asked and answered is not ours to delete.
    assert db.get(FollowUp, answered.id) is not None


def test_dedupe_is_safe_to_run_twice(db):
    """It runs on every boot."""
    from app import db as dbmod

    problem = _problem(db)
    db.add_all([FollowUp(problem_id=problem.id, due_on=date(2026, 10, 28)),
                FollowUp(problem_id=problem.id, due_on=date(2026, 11, 4))])
    db.commit()

    dbmod._dedupe_open_followups(db.get_bind())
    dbmod._dedupe_open_followups(db.get_bind())
    db.expire_all()

    assert len(_open_followups(db, problem)) == 1
