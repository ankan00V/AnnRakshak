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
from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.models import ExpertProfile, Farm, User  # noqa: E402

# (name, lang, crop, variety, sowing, district, lat, lon, acres, soil)
FARMS = [
    # Vidarbha rice belt — a three-farm cluster near Bhandara for spread alerts.
    ("Sunita Bhoyar", "mr", "rice", "Sakoli-8", date(2026, 6, 28), "Bhandara", 21.170, 79.650, 2.5, "clay loam"),
    ("Ramesh Kapgate", "mr", "rice", "Sakoli-8", date(2026, 6, 30), "Bhandara", 21.188, 79.668, 1.5, "clay loam"),
    ("Vandana Meshram", "hi", "rice", "MTU-1010", date(2026, 7, 2), "Bhandara", 21.152, 79.631, 3.0, "clay"),
    ("Anil Rahangdale", "hi", "rice", "MTU-1010", date(2026, 6, 25), "Gondia", 21.460, 80.190, 4.0, "clay loam"),
    ("Kavita Wadhai", "mr", "rice", "Sindewahi-1", date(2026, 7, 1), "Chandrapur", 19.960, 79.300, 2.0, "loam"),
    # Konkan rice.
    ("Prakash Sawant", "mr", "rice", "Ratnagiri-24", date(2026, 6, 20), "Ratnagiri", 16.990, 73.310, 1.0, "laterite"),
    ("Manisha Vartak", "mr", "rice", "Karjat-3", date(2026, 6, 22), "Palghar", 19.700, 72.770, 1.5, "laterite"),
    ("Sanjay Chougule", "mr", "rice", "Indrayani", date(2026, 7, 5), "Kolhapur", 16.700, 74.240, 2.0, "black"),
    # Marathwada / Khandesh maize — a cluster near Chhatrapati Sambhajinagar.
    ("Dnyaneshwar Jadhav", "mr", "maize", "hybrid", date(2026, 7, 4), "Chhatrapati Sambhajinagar", 19.880, 75.340, 3.0, "black"),
    ("Shobha Kale", "mr", "maize", "hybrid", date(2026, 7, 8), "Chhatrapati Sambhajinagar", 19.902, 75.361, 2.0, "black"),
    ("Imran Shaikh", "hi", "maize", "hybrid", date(2026, 7, 6), "Chhatrapati Sambhajinagar", 19.861, 75.322, 4.5, "medium black"),
    ("Yogesh Patil", "mr", "maize", "hybrid", date(2026, 7, 10), "Jalgaon", 21.000, 75.560, 5.0, "medium black"),
    ("Lata Pawar", "mr", "maize", "hybrid", date(2026, 7, 12), "Satara", 17.680, 74.000, 2.0, "medium black"),
    ("Ganesh Kolte", "en", "maize", "hybrid", date(2026, 7, 15), "Pune", 18.520, 73.860, 1.5, "medium black"),
    # Vidarbha cotton.
    ("Vijay Thakre", "mr", "cotton", "Bt hybrid", date(2026, 6, 15), "Yavatmal", 20.390, 78.120, 5.0, "black"),
    ("Pushpa Rathod", "hi", "cotton", "Bt hybrid", date(2026, 6, 18), "Yavatmal", 20.412, 78.139, 3.5, "black"),
    ("Mahesh Deshmukh", "mr", "cotton", "Bt hybrid", date(2026, 6, 20), "Amravati", 20.930, 77.750, 6.0, "black"),
    # Marathwada soybean.
    ("Balaji Shinde", "mr", "soybean", "JS 335", date(2026, 6, 28), "Latur", 18.400, 76.560, 4.0, "medium black"),
    ("Sarika Mane", "mr", "soybean", "JS 93-05", date(2026, 7, 1), "Latur", 18.421, 76.579, 2.5, "medium black"),
    ("Nitin Wankhede", "mr", "soybean", "JS 335", date(2026, 6, 25), "Nanded", 19.150, 77.310, 3.0, "black"),
]


OFFICERS_PER_DISTRICT = 5

# Surnames common in Vidarbha and Marathwada, so the queue reads like a real office.
OFFICER_NAMES = ["Deshmukh", "Wankhede", "Ingle", "Patil", "Gaikwad", "Rathod", "Shelke", "Bhoyar"]
DESIGNATIONS = ["kvk_scientist", "agriculture_officer", "agriculture_officer", "agronomist", "kvk_scientist"]


def seed_officers(db, districts: list[str]) -> int:
    """Five officers per district, verified, each covering only their own."""
    made = 0
    for d, district in enumerate(sorted(districts)):
        for i in range(OFFICERS_PER_DISTRICT):
            surname = OFFICER_NAMES[(d + i) % len(OFFICER_NAMES)]
            slug = f"{district.lower().replace(' ', '')}{i + 1}"
            u = User(role="expert", name=f"{'Dr. ' if i == 0 else ''}{surname}",
                     email=f"officer.{slug}@krishi.test", lang="mr", is_demo=True)
            db.add(u)
            db.flush()
            db.add(ExpertProfile(
                user_id=u.id, designation=DESIGNATIONS[i % len(DESIGNATIONS)],
                organisation=f"KVK {district}", employee_id=f"MH-{district[:3].upper()}-{i + 1:03d}",
                qualification="phd" if i == 0 else "msc_agri", experience_years=14 - 2 * i,
                districts=[district], crops=["rice", "maize", "cotton", "soybean"],
                specialities=["plant_pathology", "entomology"], languages=["mr", "hi", "en"],
                verified=True))
            made += 1
    return made


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
