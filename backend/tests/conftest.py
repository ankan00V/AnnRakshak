import os
import sys
import tempfile
from pathlib import Path

# Point the app at a throwaway data dir BEFORE app.config is imported.
_tmp = tempfile.mkdtemp(prefix="annrakshak-test-")
os.environ["ANNRAKSHAK_DATA_DIR"] = _tmp
# Hermetic: never call the paid Sarvam API from tests (load_dotenv does not
# override an already-set variable, so an empty value wins over .env).
os.environ["SARVAM_API_KEY"] = ""
os.environ["SARVAM_API_KEYS"] = ""
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
os.environ["ANNRAKSHAK_DB_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
