"""Which officer gets the next case.

A district has several verified officers (five, in the districts we seed). A
case that a farmer is waiting on should go to whoever can look at it soonest,
which is not the same as whoever is next in a rota: an officer already holding
eight open cases will get to a ninth later than one holding two.

So the rule, in order:

  1. the fewest open cases;
  2. then the one who has been free longest — their last case was assigned or
     resolved furthest back, and an officer who has never held one has been
     free longest of all;
  3. then the lowest user id, so the choice is deterministic and a test can
     assert it.

Pure: the caller gathers the candidates and writes the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# An officer who has never been given a case has been waiting since before the
# system existed, so they win any tie on idleness.
NEVER = datetime.min


@dataclass(frozen=True)
class Candidate:
    user_id: int
    open_cases: int
    last_active: datetime | None
    """When this officer last had a case assigned or resolved one. None = never."""


def pick(candidates: list[Candidate]) -> int | None:
    """The officer to hand the next case to, or None when there is nobody."""
    if not candidates:
        return None
    return min(candidates, key=lambda c: (c.open_cases, c.last_active or NEVER, c.user_id)).user_id


def loads(candidates: list[Candidate]) -> dict[int, int]:
    """Open cases per officer — what the dashboard shows as the district's load."""
    return {c.user_id: c.open_cases for c in candidates}
