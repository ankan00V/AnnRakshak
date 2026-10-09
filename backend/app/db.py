from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATA_DIR, DB_URL


class Base(DeclarativeBase):
    pass


def normalise_url(url: str) -> str:
    """postgres:// and postgresql:// (as Neon and Heroku print them) -> the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str = DB_URL):
    url = normalise_url(url)
    if url.startswith("sqlite"):
        if url.startswith("sqlite:///"):
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            # SQLite ignores FOREIGN KEY and CHECK-backed invariants unless asked.
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    # Postgres (Neon). The pooled endpoint is PgBouncer in transaction mode, which
    # breaks server-side prepared statements; Neon also suspends idle compute, so
    # connections are checked before use and recycled.
    return create_engine(url, pool_pre_ping=True, pool_recycle=300, pool_size=5, max_overflow=10,
                         connect_args={"prepare_threshold": None, "connect_timeout": 15})


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns added after the first release. create_all() does not alter existing
# tables, so add any that an older database lacks (SQLite ADD COLUMN is cheap).
ADDED_COLUMNS = {
    "farm": {"soil_ph": "FLOAT", "soil_ph_on": "DATE", "email": "VARCHAR(200)",
             "email_pref": "VARCHAR(10) DEFAULT 'warnings'", "email_token": "VARCHAR(40)",
             "agro_polygon_id": "VARCHAR(40)", "user_id": "INTEGER REFERENCES app_user(id)",
             "irrigation": "VARCHAR(20)", "location_source": "VARCHAR(10)", "state": "VARCHAR(60)", "taluka": "VARCHAR(80)",
             "date_basis": "VARCHAR(12) DEFAULT 'sown'"},
    "alert": {"notified_at": "DATETIME", "emailed_at": "DATETIME",
              "advisory_id": "INTEGER REFERENCES officer_advisory(id)"},
    "case": {"assigned_to": "INTEGER REFERENCES app_user(id)", "assigned_at": "DATETIME",
             "snoozed_until": "DATETIME"},
    "farmer_profile": {"state": "VARCHAR(60)"},
    "expert_profile": {"supervisor": "BOOLEAN DEFAULT FALSE"},
    "sensor_reading": {"soil_ph": "FLOAT", "soil_moisture_pct": "FLOAT"},
}


# Columns that outgrew their original width. create_all() never alters an
# existing column, and SQLite does not enforce a VARCHAR length at all, so a
# column too narrow for real data fails only against Postgres, in production.
WIDENED_COLUMNS = {
    "diagnosis": {"model_version": 255},
    "live_scan": {"model_version": 255},
}


def _widen_columns(eng, insp) -> None:
    """Grow any column that is narrower than the model now asks for.

    Postgres only: SQLite stores a string whatever the declared length says,
    and cannot ALTER a column type in place. Widening never loses data, and
    the check makes it a no-op once applied."""
    from sqlalchemy import text  # noqa: PLC0415

    if eng.dialect.name != "postgresql":
        return
    with eng.begin() as conn:
        for table, cols in WIDENED_COLUMNS.items():
            have = {c["name"]: c for c in insp.get_columns(table)}
            for col, want in cols.items():
                now = getattr(have.get(col, {}).get("type"), "length", None)
                if now is not None and now < want:
                    conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN {col} TYPE VARCHAR({want})'))


def init_db(bind=None) -> None:
    from sqlalchemy import inspect, text  # noqa: PLC0415

    from app import models  # noqa: F401  registers the tables

    eng = bind or engine
    Base.metadata.create_all(bind=eng)
    insp = inspect(eng)
    with eng.begin() as conn:
        for table, cols in ADDED_COLUMNS.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for col, typ in cols.items():
                if eng.dialect.name == "postgresql":
                    typ = typ.replace("DATETIME", "TIMESTAMP")
                if col not in have:
                    # `case` is a reserved SQL keyword; quote the table name.
                    conn.execute(text(f"ALTER TABLE \"{table}\" ADD COLUMN {col} {typ}"))
    _widen_columns(eng, insp)
    _backfill_expert_ranks(eng)


# Designation ids that were in use before the sign-up form fixed the vocabulary.
RENAMED_DESIGNATIONS = {"agriculture_officer": "agri_officer", "agronomist": "private_agronomist"}
SUPERVISOR_DESIGNATIONS = ("agri_officer", "kvk_scientist")
"""The posts that carry a supervisor's authority: the Agriculture Officer of a
taluka or district, and the KVK scientist who heads the subject-matter team.
Verifying a colleague, routing a backlog and moving another officer's cases are
theirs. Everyone else advises."""


def _backfill_expert_ranks(bind) -> None:
    """Give older databases the designation ids and the supervisor rank.

    Both columns arrived after the demo districts were seeded, so in a database
    made before them every profile kept `supervisor`'s `DEFAULT FALSE` and a
    designation id the sign-up vocabulary no longer lists. The effect was not
    cosmetic: with no supervisor anywhere, nobody could route a backlog, verify
    a colleague or move another desk's cases, and a designation outside the
    vocabulary rendered as a blank label.

    Renaming is safe to repeat. Granting the rank is not, because a district
    office may since have demoted somebody on purpose, so it runs only while
    the database holds no supervisor at all -- precisely the broken state.
    """
    from sqlalchemy import text  # noqa: PLC0415

    with bind.begin() as conn:
        for old, new in RENAMED_DESIGNATIONS.items():
            conn.execute(text("UPDATE expert_profile SET designation = :new WHERE designation = :old"),
                         {"new": new, "old": old})
        if conn.scalar(text("SELECT 1 FROM expert_profile WHERE supervisor LIMIT 1")):
            return
        posts = ", ".join(f":d{i}" for i in range(len(SUPERVISOR_DESIGNATIONS)))
        conn.execute(
            text(f"UPDATE expert_profile SET supervisor = TRUE WHERE designation IN ({posts})"),
            {f"d{i}": d for i, d in enumerate(SUPERVISOR_DESIGNATIONS)},
        )
