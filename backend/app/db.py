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
             "date_basis": "VARCHAR(12) DEFAULT 'sown'",
             "status": "VARCHAR(10) DEFAULT 'growing'", "harvested_on": "DATE",
             "season_check_on": "DATE", "harvest_seen_on": "DATE",
             "season_no": "INTEGER DEFAULT 1"},
    "alert": {"season_no": "INTEGER DEFAULT 1", "notified_at": "DATETIME", "emailed_at": "DATETIME",
              "advisory_id": "INTEGER REFERENCES officer_advisory(id)"},
    "case": {"assigned_to": "INTEGER REFERENCES app_user(id)", "assigned_at": "DATETIME",
             "snoozed_until": "DATETIME", "response_due_at": "DATETIME",
             "handovers": "INTEGER DEFAULT 0", "passed_over": "JSON"},
    "problem": {"season_no": "INTEGER DEFAULT 1"},
    "trap_reading": {"season_no": "INTEGER DEFAULT 1"},
    "live_scan": {"season_no": "INTEGER DEFAULT 1"},
    "spray_log": {"season_no": "INTEGER DEFAULT 1"},
    "notice": {"season_no": "INTEGER DEFAULT 1"},
    "season": {"season_no": "INTEGER DEFAULT 1"},
    "app_user": {"email_pref": "VARCHAR(10)"},
    "farmer_profile": {"state": "VARCHAR(60)"},
    "expert_profile": {"supervisor": "BOOLEAN DEFAULT FALSE",
                       "department": "VARCHAR(30)", "office_address": "VARCHAR(240)",
                       "block": "VARCHAR(80)", "state": "VARCHAR(60)", "pincode": "VARCHAR(6)",
                       "office_phone": "VARCHAR(20)", "joined_service_on": "DATE",
                       "posted_since": "DATE", "reporting_name": "VARCHAR(120)",
                       "reporting_designation": "VARCHAR(60)", "reporting_contact": "VARCHAR(120)",
                       "declared_at": "DATETIME"},
    "sensor_reading": {"season_no": "INTEGER DEFAULT 1", "soil_ph": "FLOAT", "soil_moisture_pct": "FLOAT"},
}


# Columns that outgrew their original width. create_all() never alters an
# existing column, and SQLite does not enforce a VARCHAR length at all, so a
# column too narrow for real data fails only against Postgres, in production.
ADDED_INDEXES = {
    # name -> (table, column). The name is the one SQLAlchemy gives an
    # index=True column, so a database created fresh and one migrated here end
    # up identical.
    #
    # farm.user_id: every farm list and every ownership check starts with
    # "whose is it".
    # diagnosis.image_path: /media/{name} finds the farm behind a photograph
    # by this column, on every image the app shows — without the index that is
    # a scan of every diagnosis ever made, per image.
    "ix_farm_user_id": ("farm", "user_id"),
    "ix_diagnosis_image_path": ("diagnosis", "image_path"),
}

WIDENED_COLUMNS = {
    "diagnosis": {"model_version": 255, "gate_reason": 80},
    "live_scan": {"model_version": 255},
    "case": {"reason": 80},
    "farm": {"date_basis": 20},
    "alert": {"trigger": 40},
    "observation": {"answer": 500},
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


def _add_indexes(eng, insp) -> None:
    """Create the indexes a table gained after it was first created.

    create_all() builds a table's indexes with the table. A column that grew an
    index later — because the query that reads it turned out to be on a hot
    path — does not get one on a database that already exists, and nothing
    says so: it stays correct and gets slower. CREATE INDEX IF NOT EXISTS is
    understood by both SQLite and Postgres, so this is the same one line for
    either."""
    from sqlalchemy import text  # noqa: PLC0415

    with eng.begin() as conn:
        for name, (table, col) in ADDED_INDEXES.items():
            if table not in insp.get_table_names():
                continue
            if any(ix["name"] == name for ix in insp.get_indexes(table)):
                continue
            conn.execute(text(f'CREATE INDEX IF NOT EXISTS {name} ON "{table}" ({col})'))


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
    _add_indexes(eng, insp)
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
