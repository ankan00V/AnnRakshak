"""Re-reading the open queue with the model that is actually deployed.

The bug this exists for: a case is a request for an expert's time, made by the
model that was live when the photo arrived. Deploying a new model left those
requests untouched, so the queue carried decisions the current model would not
make -- after v9 shipped, all but one open case had been decided by a model two
generations old, three of them a photograph of a person.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app import redecide, services
from app.config import UPLOAD_DIR
from app.db import Base, SessionLocal, engine
from app.engine import gate, vision
from app.kb import get_kb
from app.models import Case, Diagnosis, Farm, OfficerAction, Problem

SOWN = date.today() - timedelta(days=60)
LIVE = "live-model-2"
OLD = "old-model-1"


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as s:
        yield s


def _case(db, reason="CROP_MISMATCH", crop="rice", image="reread.jpg", model=OLD):
    """A farm, a photo, a reading from an older model, and the case it opened."""
    farm = Farm(farmer_name="Sunita", crop=crop, sowing_date=SOWN, district="Bhandara",
                lat=21.17, lon=79.65, area_acres=2, is_demo=True)
    db.add(farm)
    db.flush()
    problem = Problem(farm_id=farm.id, status="open")
    db.add(problem)
    db.flush()
    db.add(Diagnosis(problem_id=problem.id, image_path=image,
                     topk=[{"target": "maize_fall_armyworm", "confidence": 0.66}],
                     gate_outcome="escalate", gate_reason=reason, confidence=0.66,
                     model_version=model, is_stub=False))
    case = Case(problem_id=problem.id, status="open", reason=reason)
    db.add(case)
    db.commit()
    return case


@pytest.fixture()
def photo():
    """A real file on disk, because the pass reads the photo back."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / "reread.jpg"
    from PIL import Image
    Image.new("RGB", (64, 64), (40, 120, 50)).save(path, "JPEG")
    yield path
    path.unlink(missing_ok=True)


def _decide_as(monkeypatch, outcome, reason, *, target="rice_brown_spot", confidence=0.9):
    """Pin the live model and what the gate makes of it, so each policy branch
    can be asserted without depending on a checkpoint being present."""
    monkeypatch.setattr(vision, "model_status", lambda: {"is_stub": False, "model_version": LIVE})
    monkeypatch.setattr(vision, "classify", lambda *a, **k: gate.TopK(
        [gate.Prediction(target, confidence), gate.Prediction("rice_hispa", 0.02)], LIVE, False))
    monkeypatch.setattr(redecide.prior, "apply_prior", lambda topk, counts: topk)
    monkeypatch.setattr(redecide.gate, "decide", lambda *a, **k: gate.GateDecision(
        outcome, reason, confidence, 0.7, [gate.Prediction(target, confidence)]))


def test_a_photo_that_is_not_a_crop_withdraws_the_case(db, photo, monkeypatch):
    """Three of the real stale cases were a photograph of a person. Nobody
    should spend an expert's morning on one."""
    case = _case(db)
    _decide_as(monkeypatch, "retake", "NOT_A_CROP_PHOTO")

    rows = redecide.redecide(db, get_kb(), apply=True)

    assert [r.action for r in rows] == [redecide.WITHDRAWN]
    db.expire_all()
    assert db.get(Case, case.id).status == "resolved"
    assert db.get(Case, case.id).resolved_at is not None
    assert db.get(Problem, case.problem_id).status == "resolved"


def test_a_case_that_is_still_an_experts_call_keeps_its_place_with_a_current_reason(db, photo, monkeypatch):
    case = _case(db, reason="CROP_MISMATCH")
    _decide_as(monkeypatch, "escalate", "UNFAMILIAR_PHOTO")

    rows = redecide.redecide(db, get_kb(), apply=True)

    assert [r.action for r in rows] == [redecide.REASON_UPDATED]
    db.expire_all()
    assert db.get(Case, case.id).status == "open"          # still waiting on a human
    assert db.get(Case, case.id).reason == "UNFAMILIAR_PHOTO"


def test_a_model_that_is_now_confident_does_not_advise_the_farmer_by_itself(db, photo, monkeypatch):
    """The sharp edge of this pass. No farmer is standing here to receive
    advice, and an advisory schedules a follow-up and notifies them, so the
    case stays open for an officer to confirm."""
    from app.models import Advisory, FollowUp

    case = _case(db, reason="BELOW_GATE")
    _decide_as(monkeypatch, "advise", "ABOVE_GATE")

    rows = redecide.redecide(db, get_kb(), apply=True)

    assert [r.action for r in rows] == [redecide.NOTED]
    db.expire_all()
    assert db.get(Case, case.id).status == "open"
    assert db.get(Case, case.id).reason == "BELOW_GATE"    # untouched; a human decides
    assert db.get(Problem, case.problem_id).target is None
    assert db.scalars(select(Advisory)).all() == []
    assert db.scalars(select(FollowUp)).all() == []


def test_the_new_reading_is_what_an_officer_sees_and_the_old_one_survives(db, photo, monkeypatch):
    case = _case(db, reason="BELOW_GATE")
    _decide_as(monkeypatch, "escalate", "BELOW_FLOOR")

    redecide.redecide(db, get_kb(), apply=True)

    db.expire_all()
    diags = db.scalars(select(Diagnosis).where(Diagnosis.problem_id == case.problem_id)
                       .order_by(Diagnosis.id)).all()
    assert [d.model_version for d in diags] == [OLD, LIVE]      # both on the record
    newest = services._latest(db, Diagnosis, [case.problem_id])[case.problem_id]
    assert newest.model_version == LIVE                          # and the officer reads this one


def test_a_dry_run_changes_nothing(db, photo, monkeypatch):
    case = _case(db, reason="CROP_MISMATCH")
    _decide_as(monkeypatch, "retake", "NOT_A_CROP_PHOTO")

    rows = redecide.redecide(db, get_kb(), apply=False)

    assert [r.action for r in rows] == [redecide.WITHDRAWN]      # it still says what it would do
    db.expire_all()
    assert db.get(Case, case.id).status == "open"
    assert len(db.scalars(select(Diagnosis)).all()) == 1


def test_a_case_already_read_by_the_live_model_is_left_alone(db, photo, monkeypatch):
    _case(db, model=LIVE)
    _decide_as(monkeypatch, "retake", "NOT_A_CROP_PHOTO")

    assert redecide.redecide(db, get_kb(), apply=True) == []


def test_a_missing_photo_is_skipped_rather_than_guessed(db, monkeypatch):
    """The photo is the evidence; without it the old decision is all there is."""
    case = _case(db, image="gone.jpg")
    _decide_as(monkeypatch, "retake", "NOT_A_CROP_PHOTO")

    rows = redecide.redecide(db, get_kb(), apply=True)

    assert [r.action for r in rows] == [redecide.SKIPPED]
    db.expire_all()
    assert db.get(Case, case.id).status == "open"


def test_a_crop_the_model_cannot_read_is_not_given_a_reading(db, photo, monkeypatch):
    """`services.diagnose` refuses before the classifier for these, and so
    must this, or the queue fills with readings the live app never produces."""
    kb = get_kb()
    not_photo = next((c for c, v in kb.crops.items() if not v["photo_diagnosis"]), None)
    if not_photo is None:
        pytest.skip("every crop in the knowledge base is photo-diagnosable")
    case = _case(db, crop=not_photo, reason="CROP_NOT_SUPPORTED")
    _decide_as(monkeypatch, "advise", "ABOVE_GATE")

    rows = redecide.redecide(db, get_kb(), apply=True)

    assert [r.action for r in rows] == [redecide.SKIPPED]
    db.expire_all()
    assert db.get(Case, case.id).reason == "CROP_NOT_SUPPORTED"


def test_a_stub_must_not_re_decide_a_real_queue(db, photo, monkeypatch):
    _case(db)
    monkeypatch.setattr(vision, "model_status", lambda: {"is_stub": True, "model_version": "stub-0"})
    with pytest.raises(RuntimeError, match="stub"):
        redecide.redecide(db, get_kb(), apply=True)


def test_every_change_is_written_into_the_offices_own_record(db, photo, monkeypatch):
    case = _case(db, reason="CROP_MISMATCH")
    _decide_as(monkeypatch, "escalate", "UNFAMILIAR_PHOTO")

    redecide.redecide(db, get_kb(), apply=True)

    db.expire_all()
    line = db.scalars(select(OfficerAction).where(OfficerAction.action == "redecide")).one()
    assert line.actor_name == "system"
    assert line.subject_id == case.id
    assert line.detail["was"] == "CROP_MISMATCH"          # the reason it carried, not the new one
    assert line.detail["now"] == "UNFAMILIAR_PHOTO"
    assert (line.detail["from_model"], line.detail["to_model"]) == (OLD, LIVE)
