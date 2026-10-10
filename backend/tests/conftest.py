import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

# Point the app at a throwaway data dir BEFORE app.config is imported.
_tmp = tempfile.mkdtemp(prefix="annrakshak-test-")
os.environ["ANNRAKSHAK_DATA_DIR"] = _tmp
# Hermetic: never call the paid Sarvam API from tests (load_dotenv does not
# override an already-set variable, so an empty value wins over .env).
os.environ["SARVAM_API_KEY"] = ""
os.environ["SARVAM_API_KEYS"] = ""
os.environ["BHASHINI_INFERENCE_KEY"] = ""  # same for Bhashini: tests never call the platform
# Deterministic stub scenarios, even when a trained model sits in ml/artifacts.
os.environ["ANNRAKSHAK_VISION"] = "stub"
# Krishi's matcher and its fallbacks are what the tests pin down; the model that
# reads messy questions is a network call and would make them flaky and slow.
os.environ["ANNRAKSHAK_NIM"] = "off"
# No background watcher, no real weather key, no real email in tests.
os.environ["ANNRAKSHAK_WATCH"] = "off"
os.environ["OPENWEATHER_API_KEY"] = ""
os.environ["AGRO_API_KEY"] = ""
os.environ["EMAIL_BACKEND"] = "outbox"
os.environ["SMTP_HOST"] = ""
os.environ["REDIS_URL"] = ""  # in-process fallbacks; never the shared Redis
os.environ["ANNRAKSHAK_AUTH"] = "off"  # the older flow tests; tests/test_auth.py switches it on
# Tests never touch the cloud database or Redis from .env.
#
# SQLite by default, because it is fast and needs nothing installed. But it
# does not enforce a VARCHAR length and Postgres does, which is how a column
# two characters too narrow passed every test here and then lost a day of
# photo diagnoses in production. Set ANNRAKSHAK_TEST_DB_URL to run the same
# suite against a real Postgres; CI does, so that class of bug fails here.
#
# The suite drops every table it finds, so the override is only honoured for a
# database that is plainly disposable: on this machine, or named for testing.
# The production database is none of those and cannot be reached this way.
_requested = os.environ.get("ANNRAKSHAK_TEST_DB_URL", "").strip()
if _requested:
    _parts = urlsplit(_requested)
    _host = (_parts.hostname or "").lower()
    _dbname = _parts.path.lstrip("/").lower()
    _disposable = (_requested.startswith("sqlite")
                   or _host in ("localhost", "127.0.0.1", "::1", "postgres", "db")
                   or "test" in _dbname)
    if not _disposable:
        raise SystemExit(
            f"ANNRAKSHAK_TEST_DB_URL points at {_host or 'an unnamed host'}/{_dbname or '?'}, which does not "
            "look like a throwaway database. This suite drops every table. Use a local Postgres, or a "
            "database whose name contains 'test'.")
    os.environ["ANNRAKSHAK_DB_URL"] = _requested
else:
    os.environ["ANNRAKSHAK_DB_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
