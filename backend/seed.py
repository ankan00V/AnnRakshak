"""Demo farms across Maharashtra's rice, maize, cotton and soybean belts.

    .venv/bin/python backend/seed.py            # add farms if the table is empty
    .venv/bin/python backend/seed.py --reset    # wipe the database first

Farms and the district officers who review their cases are seeded, all flagged
is_demo. Diagnoses, cases, confirmations and alerts come from running the real
flows — nothing on the officials' dashboard is invented. Farms are clustered a
few km apart so a confirmed case has neighbours inside the spread radius.

Each district gets five verified officers, because that is what routing is for:
an escalation goes to whichever of them is carrying the least (app.engine.assign).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import func, select  # noqa: E402

from app.config import DB_URL  # noqa: E402
from app.db import SUPERVISOR_DESIGNATIONS, Base, SessionLocal, engine, init_db  # noqa: E402
from app.models import ExpertProfile, Farm, User  # noqa: E402

# (name, lang, crop, variety, sowing, district, lat, lon, acres, soil)
#
# One farm per crop, in the district that crop is actually grown in. The demo
# used to carry twenty — eight rice farms, six maize — which made the farmer's
# own first screen a list to read rather than a choice to make, and filled the
# office with other people's fields.
#
# What that costs, so it is not discovered at a demo: a confirmed case spreads
# a warning to farms of the same crop within SPREAD_RADIUS_KM (5 km), and with
# one farm per crop there is never a second farm to warn. Put a neighbour back
# — same crop, a hundredth of a degree away — and that half of the story works
# again.
FARMS = [
    ("Sunita Bhoyar", "mr", "rice", "Sakoli-8", date(2026, 6, 28), "Bhandara", 21.170, 79.650, 2.5, "clay loam"),
    ("Dnyaneshwar Jadhav", "mr", "maize", "hybrid", date(2026, 7, 4), "Chhatrapati Sambhajinagar", 19.880, 75.340, 3.0, "black"),
    ("Vijay Thakre", "mr", "cotton", "Bt hybrid", date(2026, 6, 15), "Yavatmal", 20.390, 78.120, 5.0, "black"),
    ("Balaji Shinde", "mr", "soybean", "JS 335", date(2026, 6, 28), "Latur", 18.400, 76.560, 4.0, "medium black"),
]


def seed_officers(db, districts: list[str]) -> int:
    """One demo officer, covering the demo districts.

    A real district office staffs five to a district and the queue hands the
    next case to the freest of them; that rule lives in the engine
    (app.engine.assign) and applies to every officer who signs up for real. It
    does not need to be acted out in the demo. Sixty-five seeded names only
    made the roster a page to scroll and put other people's names on the cases
    a visitor opened.
    """
    u = User(role="expert", name="Dr. Kale", email="officer.demo@krishi.test", lang="mr", is_demo=True)
    db.add(u)
    db.flush()
    db.add(ExpertProfile(
        user_id=u.id, designation="kvk_scientist", organisation=f"KVK {sorted(districts)[0]}",
        employee_id="MH-DEMO-001", qualification="phd", experience_years=14,
        districts=sorted(districts), crops=["rice", "maize", "cotton", "soybean"],
        specialities=["plant_pathology", "entomology"], languages=["mr", "hi", "en"],
        verified=True,
        # The rank follows the post, exactly as it does for a real sign-up.
        supervisor="kvk_scientist" in SUPERVISOR_DESIGNATIONS))
    return 1


def main() -> None:
    if "--reset" in sys.argv:
        Base.metadata.drop_all(bind=engine)
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(func.count(Farm.id))):
            print("farms already present; use --reset to start over")
            return
        for name, lang, crop, variety, sown, district, lat, lon, acres, soil in FARMS:
            db.add(Farm(farmer_name=name, lang=lang, crop=crop, variety=variety, sowing_date=sown,
                        district=district, lat=lat, lon=lon, area_acres=acres, soil=soil, is_demo=True))
        districts = sorted({f[5] for f in FARMS})
        officers = seed_officers(db, districts)
        db.commit()
        print(f"seeded {len(FARMS)} demo farms and {officers} officers "
              f"across {len(districts)} districts into {DB_URL}")


if __name__ == "__main__":
    main()
