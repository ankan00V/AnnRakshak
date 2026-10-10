"""Re-read the open queue with the model that is actually deployed.

A case is a request for an expert's time, made by the model that was live when
the photo arrived. Deploy a new model and those requests stay exactly as they
were: the queue carries decisions the current model would not make, and an
officer spends their morning on them. When v9 shipped, 27 of the 28 open cases
had been decided by a model two generations old, and the queue read as a wall
of CROP_MISMATCH that the live model does not produce for those photos --
three of them were a photograph of a person, which the current model rejects
outright as not a crop photo.

This re-runs each stored photo through the live pipeline -- the same classify,
prior and gate that `services.diagnose` uses, in the same order -- and records
the reading as another Diagnosis row. `services._latest` takes the newest row
per problem, so an officer opening the case sees the current verdict while the
original stays on the record.

What it does with that reading is deliberately narrow:

  retake    the photo is not a crop photo at all. Withdraw the case; nobody
            should spend an expert's morning on a selfie.
  escalate  still an expert's call. Keep the case and update its reason, so the
            officer reads why it is in front of them now rather than why it was
            in September.
  advise /  the model is confident now, but no farmer is standing here to
  clarify   receive advice or answer a clarifying question, and an advisory
            schedules a follow-up and notifies them. Leave the case open with
            the new reading attached, for an officer to confirm in one press.

Nothing here invents a verdict: no advisory is composed, no label prior is
taught, no farmer is messaged. Those all belong to a human pressing a button.

Dry run by default. `python -m app.redecide` prints what would change;
`python -m app.redecide --apply` writes it.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import office, services
from app.config import UPLOAD_DIR
from app.db import SessionLocal
from app.engine import gate, prior, vision
from app.kb import KB, get_kb
from app.models import Case, Diagnosis, Farm, Problem

WITHDRAWN = "withdrawn"
REASON_UPDATED = "reason_updated"
NOTED = "noted"
UNCHANGED = "unchanged"
SKIPPED = "skipped"


@dataclass
class Reread:
    """One case, as it was and as the live model reads it."""

    case_id: int
    problem_id: int
    was: str
    """The gate reason the case was opened with."""
    now: str
    """The gate reason the live model gives, or why it could not be read."""
    action: str
    old_model: str
    new_model: str | None = None


def _newest_diagnosis(db: Session, problem_id: int) -> Diagnosis | None:
    return db.scalars(
        select(Diagnosis).where(Diagnosis.problem_id == problem_id).order_by(Diagnosis.id.desc())
    ).first()


def stale(db: Session, model_version: str, *, demo: bool | None = None) -> list[Case]:
    """Open cases whose most recent reading came from another model."""
    q = (select(Case).join(Problem, Problem.id == Case.problem_id)
         .join(Farm, Farm.id == Problem.farm_id)
         .where(Case.status == "open").order_by(Case.id))
    if demo is not None:
        q = q.where(Farm.is_demo.is_(demo))
    out = []
    for case in db.scalars(q).all():
        diag = _newest_diagnosis(db, case.problem_id)
        if diag is not None and diag.model_version != model_version:
            out.append(case)
    return out


def redecide(db: Session, kb: KB, *, apply: bool = False, demo: bool | None = None,
             limit: int | None = None) -> list[Reread]:
    """Re-read every stale open case. Writes only when `apply` is true."""
    status = vision.model_status()
    if status["is_stub"]:
        raise RuntimeError("no real model is loaded; a stub must not re-decide a real queue")
    live = status["model_version"]

    results: list[Reread] = []
    cases = stale(db, live, demo=demo)[: limit or None]
    for case in cases:
        problem = db.get(Problem, case.problem_id)
        farm = db.get(Farm, problem.farm_id)
        old = _newest_diagnosis(db, problem.id)
        was = case.reason  # read before anything below can change it
        path = UPLOAD_DIR / old.image_path if old and old.image_path else None

        if path is None or not path.exists():
            # The photo is the evidence. Without it the old decision is all
            # there is, and it stays untouched.
            results.append(Reread(case.id, problem.id, was, "photo missing", SKIPPED,
                                  old.model_version if old else "?"))
            continue

        if not kb.crops[farm.crop]["photo_diagnosis"]:
            # `services.diagnose` refuses before the classifier for these, and
            # so must this: a crop the model was never taught would otherwise
            # be given a reading here that the live app would never produce.
            # (The reverse does get re-read -- a crop that has since become
            # diagnosable is exactly the drift this pass exists for.)
            results.append(Reread(case.id, problem.id, was, "crop not photo-diagnosable", SKIPPED,
                                  old.model_version))
            continue

        raw = vision.classify(path.read_bytes(), farm.crop)
        topk = prior.apply_prior(raw, services.prior_counts(db, farm.district, farm.crop))
        decision = gate.decide(
            topk,
            farm_crop=farm.crop,
            tier_of=lambda t: kb.targets.get(t, {}).get("tier"),
            has_advisory=lambda t: t in kb.advisories,
            cue_for=kb.cue_for,
        )

        if decision.outcome == "retake":
            action = WITHDRAWN
        elif decision.outcome == "escalate":
            action = REASON_UPDATED if decision.reason != was else UNCHANGED
        else:
            action = NOTED

        results.append(Reread(case.id, problem.id, was, decision.reason, action,
                              old.model_version, topk.model_version))
        if not apply:
            continue

        db.add(Diagnosis(
            problem_id=problem.id,
            image_path=old.image_path,
            topk=[{"target": p.target, "confidence": p.confidence} for p in topk.predictions],
            gate_outcome=decision.outcome,
            gate_reason=decision.reason,
            confidence=decision.confidence,
            model_version=topk.model_version,
            is_stub=topk.is_stub,
            heatmap=topk.heatmap,
        ))
        if action == WITHDRAWN:
            now = datetime.now(UTC)
            case.status, case.resolved_at = "resolved", now
            problem.status, problem.resolved_at = "resolved", now
        elif action == REASON_UPDATED:
            case.reason = decision.reason
        office.record(db, actor=None, action="redecide", subject="case", subject_id=case.id,
                      detail={"was": was, "now": decision.reason, "outcome": decision.outcome,
                              "from_model": old.model_version, "to_model": topk.model_version,
                              "action": action})

    if apply:
        db.commit()
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--apply", action="store_true", help="write the changes (default: show them only)")
    ap.add_argument("--demo", choices=("yes", "no"), help="limit to demo farms, or to real ones")
    ap.add_argument("--limit", type=int, help="stop after this many cases")
    args = ap.parse_args()

    demo = None if args.demo is None else args.demo == "yes"
    with SessionLocal() as db:
        rows = redecide(db, get_kb(), apply=args.apply, demo=demo, limit=args.limit)

    if not rows:
        print("Every open case was decided by the model that is deployed.")
        return
    width = max(len(r.was) for r in rows)
    for r in rows:
        print(f"  case {r.case_id:<5} {r.was:<{width}} -> {r.now:<22} {r.action}")
    tally: dict[str, int] = {}
    for r in rows:
        tally[r.action] = tally.get(r.action, 0) + 1
    print(f"\n{len(rows)} stale case{'' if len(rows) == 1 else 's'}: "
          + ", ".join(f"{n} {a}" for a, n in sorted(tally.items())))
    if not args.apply:
        print("Nothing was written. Re-run with --apply.")


if __name__ == "__main__":
    main()
