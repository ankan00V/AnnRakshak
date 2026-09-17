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
             "irrigation": "VARCHAR(20)", "location_source": "VARCHAR(10)", "state": "VARCHAR(60)", "taluka": "VARCHAR(80)"},
    "alert": {"notified_at": "DATETIME", "emailed_at": "DATETIME"},
    "farmer_profile": {"state": "VARCHAR(60)"},
    "sensor_reading": {"soil_ph": "FLOAT", "soil_moisture_pct": "FLOAT"},
}


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
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
