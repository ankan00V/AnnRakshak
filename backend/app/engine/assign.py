"""Which officer gets the next case, and who gets it when they do not answer.

Nobody picks cases here and nobody hands one to a colleague. A farmer's case
is routed by this module, and the officer it lands on is the one who has to
answer it — which is the only arrangement where "nobody got to it" is a fact
the system knows rather than a thing the district finds out from the farmer.

Eligibility first, load second. In order:

  1. covers the district the farm is in;
  2. works with that crop;
  3. has the speciality the problem calls for — a disease to a pathologist, an
     insect to an entomologist;
  4. the fewest open cases;
  5. then the one who has been free longest — their last case was assigned or
     resolved furthest back, and an officer who has never held one has been
     free longest of all;
  6. then the lowest user id, so the choice is deterministic and a test can
     assert it.

The first three are preferences, not filters. A district with one officer who
does not match the speciality still gets its case answered by that officer: a
farmer waiting on a sick crop is better served by the wrong specialist today
than the right one next week. What is never relaxed is verification — an
officer the district office has not checked is not in the list at all, and
that happens where the candidates are gathered (services.officers_for).

Pure: the caller gathers the candidates and writes the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# An officer who has never been given a case has been waiting since before the
# system existed, so they win any tie on idleness.
NEVER = datetime.min

# Which speciality answers which kind of problem. A target the knowledge base
# calls a disease wants a pathologist; an insect wants an entomologist.
SPECIALITY_FOR_KIND = {"disease": "plant_pathology", "pest": "entomology",
                       "deficiency": "agronomy", "weed": "weed_science"}


@dataclass(frozen=True)
class Candidate:
    user_id: int
    open_cases: int
    last_active: datetime | None
    """When this officer last had a case assigned or resolved one. None = never."""
    covers_district: bool = True
    knows_crop: bool = True
    has_speciality: bool = True


def rank(c: Candidate) -> tuple:
    """Lower sorts first. Eligibility, then load, then idleness, then id."""
    return (not c.covers_district, not c.knows_crop, not c.has_speciality,
            c.open_cases, c.last_active or NEVER, c.user_id)


def pick(candidates: list[Candidate], exclude: set[int] | None = None) -> int | None:
    """The officer to hand the next case to, or None when there is nobody.

    `exclude` is how a case that ran out of time on one desk avoids going
    straight back to it. If excluding everyone would leave nobody, the
    exclusion is dropped rather than the case: a case with no holder is worse
    than a case back with someone who was slow once."""
    if not candidates:
        return None
    pool = [c for c in candidates if c.user_id not in (exclude or set())] or candidates
    return min(pool, key=rank).user_id


def loads(candidates: list[Candidate]) -> dict[int, int]:
    """Open cases per officer — what the dashboard shows as the district's load."""
    return {c.user_id: c.open_cases for c in candidates}
