"""Every tunable constant lives here and nowhere else.

The decision thresholds are module constants, not environment settings, so
nobody can quietly loosen them before a demo. A threshold literal in another
file is a bug.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR.parent / ".env")  # secrets only (API keys); never thresholds

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY")
SARVAM_API_KEYS = list(dict.fromkeys(
    k.strip() for k in [*(os.environ.get("SARVAM_API_KEYS") or "").split(","), SARVAM_API_KEY or ""] if k.strip()))
"""Every Sarvam key we may use, rotated; one out of credits is benched and the next takes over."""
BHASHINI_INFERENCE_KEY = os.environ.get("BHASHINI_INFERENCE_KEY")
"""MeitY Bhashini: the first choice for translation, speech and transcription
(app/bhashini.py). Sarvam, when its keys are set, is the fallback."""
BHASHINI_COMPUTE_URL = os.environ.get(
    "BHASHINI_COMPUTE_URL", "https://dhruva-api.bhashini.gov.in/services/inference/pipeline")
BHASHINI_TRANSLATE_SERVICE = "ai4bharat/indictrans-v2-all-gpu--t4"
_IA, _DR = "ai4bharat/indic-tts-coqui-indo_aryan-gpu--t4", "ai4bharat/indic-tts-coqui-dravidian-gpu--t4"
BHASHINI_TTS_SERVICE = {"en": "ai4bharat/indic-tts-coqui-misc-gpu--t4",
                        "hi": _IA, "mr": _IA, "bn": _IA, "gu": _IA, "pa": _IA, "od": _IA,
                        "ta": _DR, "te": _DR, "kn": _DR, "ml": _DR}
_ASR_IA, _ASR_DR = ("ai4bharat/conformer-multilingual-indo_aryan-gpu--t4",
                    "ai4bharat/conformer-multilingual-dravidian-gpu--t4")
BHASHINI_ASR_SERVICE = {"en": "ai4bharat/whisper-medium-en--gpu--t4", "hi": "ai4bharat/conformer-hi-gpu--t4",
                        "mr": _ASR_IA, "bn": _ASR_IA, "gu": _ASR_IA, "pa": _ASR_IA, "od": _ASR_IA,
                        "ta": _ASR_DR, "te": _ASR_DR, "kn": _ASR_DR, "ml": _ASR_DR}
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY") if os.environ.get("ANNRAKSHAK_NIM") != "off" else None
"""NVIDIA NIM, used by Krishi to understand a question — never to answer one.
Absent, Krishi falls back to its own matcher and loses nothing it can promise."""
NVIDIA_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "openai/gpt-oss-20b")
"""Chosen by measurement on 28 questions typed the way farmers actually type
(Hinglish, romanised Marathi, typos): it routed 25 right where Krishi's own
matcher managed 16, refused all 4 off-topic questions, and answers in under a
second. nemotron-3-super-120b was faster (366 ms) but got 21."""
NVIDIA_SUGGEST_KEY = (os.environ.get("NVIDIA_API_KEYS") or "").split(",")[-1].strip() or NVIDIA_API_KEY
"""The spray check's own key. It is a separate, farmer-facing call on a screen
about chemicals, and it should not go dark because Krishi used up the quota."""
NVIDIA_TIMEOUT_S = 10.0
"""Measured median 2.6 s, 90th percentile 4.8 s. A call that times out costs the
farmer the wait AND falls back anyway, so the bar is set past the slow tail."""
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
AGRO_API_KEY = os.environ.get("AGRO_API_KEY")  # AgroMonitoring: satellite NDVI and soil per field  # optional; Open-Meteo is the keyless fallback
MOSDAC_USERNAME = os.environ.get("MOSDAC_USERNAME")
MOSDAC_PASSWORD = os.environ.get("MOSDAC_PASSWORD")
"""ISRO MOSDAC account (https://mosdac.gov.in/signup/) for INSAT-3DS satellite
rainfall. Optional: without it past rain stays the weather model's estimate."""
MOSDAC_DATASET = os.environ.get("MOSDAC_DATASET", "3SIMG_L2B_HEM")
"""INSAT-3DS Hydro-Estimator rain rate; 3RIMG_L2B_HEM is INSAT-3DR's."""
SARVAM_TTS_MODEL = "bulbul:v3"
SARVAM_STT_MODEL = "saaras:v3"
SARVAM_TRANSLATE_MODEL = "sarvam-translate:v1"
SARVAM_SPEAKER = "shubh"  # bulbul:v3 default; v2 voices are rejected by v3
SARVAM_LANG = {"en": "en-IN", "hi": "hi-IN", "mr": "mr-IN", "bn": "bn-IN", "ta": "ta-IN", "te": "te-IN",
               "kn": "kn-IN", "ml": "ml-IN", "gu": "gu-IN", "pa": "pa-IN", "od": "od-IN"}
KB_DIR = BACKEND_DIR / "kb"
DATA_DIR = Path(os.environ.get("ANNRAKSHAK_DATA_DIR", BACKEND_DIR / ".data"))
UPLOAD_DIR = DATA_DIR / "uploads"
WEATHER_CACHE_DIR = DATA_DIR / "weather"
DB_URL = os.environ.get("ANNRAKSHAK_DB_URL", f"sqlite:///{DATA_DIR / 'annrakshak.db'}")

# --- Confidence gate -------------------------------------------------------
# Starting values, to be re-fit once the trained model's calibrated confidence
# distribution on a held-out field set is known.

GATE = 0.70
"""Top-1 at or above this, and clear of the runner-up by MARGIN → advise."""

FLOOR = 0.40
"""Top-1 below this → the model has nothing useful to say; escalate."""

MARGIN = 0.15
"""Minimum top-1 minus top-2 gap to call a prediction clear. Below → ask."""

MIN_VEGETATION_FRACTION = 0.08
"""Below this share of plant-coloured pixels the photo is not a crop photo and
is rejected before the classifier's softmax is trusted. A softmax with no
reject class always puts its mass somewhere, even on a photo of a shoe.
Measured on the 835 ICAR images: 10 (1.2%) fall below it, mostly insects shot
off the plant; flat wood, cardboard, soil, skin and grey all score 0."""

CLEARLY_VEGETATION = 0.35
"""At or above this share of plant-coloured pixels the photo IS of a plant,
whatever the familiarity score says. The two are independent: familiarity asks
"have I seen photos like this?", which a farmer's wide phone shot of a chewed
whorl can fail honestly. Telling that farmer "this is not a crop photo, take
another" is the worst answer the app can give, so above this bar an unfamiliar
photo goes to an expert instead of back to the farmer. Measured on the 44
out-of-scope photos in the familiarity check: 32 of them fall below it."""

TARGET_GATE = {
    "rice_blast": 0.90,
    "maize_common_rust": 0.90,
}
"""Classes learnt only from lab photos (single leaves on plain backdrops) must
clear a higher bar before the app advises them — in the photo gate and for a
'strong' view in the live walk. Measured on held-out images (2026-09-15):
rice blast precision 0.868 at the global 0.70 -> 0.957 at 0.90 (recall 0.844);
maize rust 0.963 -> 1.000 (recall 1.000); every other class 0.972 at 0.70.
Between GATE and this bar the gate asks the look-alike question or sends the
photo to an expert. Drop an entry once expert confirmations show the class
holds up on farmers' field photos."""
assert all(v >= GATE for v in TARGET_GATE.values())


def gate_for(target: str) -> float:
    return TARGET_GATE.get(target, GATE)


# --- Learning from field confirmations -------------------------------------

PRIOR_FULL_COUNT = 10
"""Net expert confirmations (confirmed minus corrected) that earn the full
PRIOR_MAX_BIAS nudge for a label in a district."""

PRIOR_MAX_BIAS = 0.05
"""Cap on the additive nudge a label's local confirmation history may apply to
a model confidence before the gate sees it."""

# The nudge must never move a prediction across a gate band on its own:
# smaller than MARGIN, it cannot turn an ambiguous pair into a clear one;
# smaller than GATE - FLOOR, it cannot carry an escalation to advice.
assert PRIOR_MAX_BIAS < MARGIN
assert PRIOR_MAX_BIAS < GATE - FLOOR

# --- Risk, spread and follow-up --------------------------------------------

SPREAD_RADIUS_KM = 5.0
"""Same-crop farms within this radius of a confirmed case get a spread alert."""

MAX_RISK_ALERTS_PER_FARM_PER_DAY = 3
"""Weather/phenology alerts per farm per day. Spread and trap alerts bypass
this: a confirmed neighbour or a trap over threshold is stronger evidence."""

WEATHER_PAST_DAYS = 7
WEATHER_FORECAST_DAYS = 7
WEATHER_TIMEOUT_S = 10
WEATHER_CACHE_MAX_AGE_H = 12
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

REDIS_URL = os.environ.get("REDIS_URL")
"""Upstash/any Redis: shared cache, rate limits, one-watcher lease, cross-instance events. Optional."""

AGRO_CACHE_MINUTES = 30
"""Hour-by-hour agro-weather is re-fetched at most this often per location."""

# --- Sign-in (OTP) and roles ------------------------------------------------

AUTH_ENFORCE = os.environ.get("ANNRAKSHAK_AUTH", "on") != "off"
"""Every farm, problem, alert and expert endpoint checks who is asking. Tests
of the older flows turn it off; the auth tests turn it on."""
DEMO_LOGIN = os.environ.get("ANNRAKSHAK_DEMO_LOGIN", "on") != "off"
"""'Try the demo' sign-in to the seeded demo farms / a demo expert. Off in production."""
OTP_CHANNEL = "email"
"""Where one-time codes go. Both roles give a mobile number at sign-up, but
there is no free SMS gateway yet, so every code is emailed (SMTP above)."""
EXPERT_AUTO_VERIFY = os.environ.get("ANNRAKSHAK_EXPERT_AUTO_VERIFY", "on") != "off"
"""Hackathon builds verify experts at sign-up; production sets this off and the district office verifies."""
OTP_DIGITS = 6
OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 30
SESSION_HOURS = 24
"""A session ends 24 hours after sign-in, however active it was; then sign in again."""
SINGLE_SESSION = True
"""Signing in ends the account's other sessions, so one account is open in one
browser at a time. Demo accounts are exempt: judges share them."""
COOKIE_SECURE = os.environ.get("ANNRAKSHAK_COOKIE_SECURE", "off") == "on"  # on behind HTTPS

# --- Notifications: in-app (SSE), phone (Web Push) and email ---------------

WATCH_ENABLED = os.environ.get("ANNRAKSHAK_WATCH", "on") != "off"
"""The background watcher (weather rules, risk run, pushes, emails). Tests turn it off."""
WATCH_MINUTES = 30
QUIET_HOURS = (21, 6)
"""Local hours [start, end) when only warnings are delivered; the rest wait for morning."""
MAX_PUSH_PER_FARM_PER_DAY = 4
"""Non-warning phone notifications per farm per day. Warnings are never held back."""
MAX_ALERT_EMAILS_PER_FARM_PER_DAY = 3
DIGEST_HOUR = 6
"""Local hour after which the daily farm summary email goes out."""
PUBLIC_APP_URL = os.environ.get("ANNRAKSHAK_PUBLIC_URL", "http://localhost:5173").rstrip("/")

# Secrets and delivery settings (from .env; see .env.example)
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")  # PEM; generated into DATA_DIR if unset
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:alerts@annrakshak.in")
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT") or 587)
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_SECURITY = os.environ.get("SMTP_SECURITY", "starttls")  # starttls | ssl | none
EMAIL_FROM = os.environ.get("EMAIL_FROM") or (f"AnnRakshak <{SMTP_USER}>" if SMTP_USER else "AnnRakshak <alerts@localhost>")
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND") or ("smtp" if SMTP_HOST else "outbox")
"""'smtp' sends; 'outbox' writes .eml files to DATA_DIR/outbox (dev and tests)."""

FOLLOWUP_DUE_DAYS = 4
CASE_ETA_MINUTES_PER_POSITION = 20
