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


def _flag(name: str, default: bool) -> bool:
    """An on/off setting, with a default that may differ in production."""
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in ("on", "1", "true", "yes")


ENV = os.environ.get("ANNRAKSHAK_ENV", "dev").strip().lower()
PROD = ENV in ("prod", "production")
"""What this process is: a laptop, or a server with farmers' data on it.

Several settings are convenient on a laptop and wrong in front of real users —
a one-tap demo sign-in, experts who verify themselves, a cookie that will
travel over plain HTTP. Each of those now defaults the safe way when
ANNRAKSHAK_ENV=production, and start_checks() below refuses to start if one of
them has been turned back on by hand without the operator saying so."""

WEB_DIR = Path(os.environ["ANNRAKSHAK_WEB_DIR"]) if os.environ.get("ANNRAKSHAK_WEB_DIR") else None
"""The built browser app, served by this process when set (the Dockerfile sets
it). One origin for the app and the API: a first-party session cookie, no CORS,
and a farmer's photographs fetched with the viewer's own session."""

ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in
                   (os.environ.get("ANNRAKSHAK_ORIGINS") or "").split(",") if o.strip()]
"""Where the browser app is served from, when that is not the same origin as
this API. Empty is the normal case: one host serves both (see the Dockerfile),
and then no cross-origin request happens at all."""

PUSH_HOSTS = tuple(h.strip().lower() for h in
                   (os.environ.get("ANNRAKSHAK_PUSH_HOSTS")
                    or "fcm.googleapis.com,android.googleapis.com,.push.services.mozilla.com,"
                       ".notify.windows.com,.push.apple.com").split(",") if h.strip())
"""Where a push subscription may point. A subscription endpoint is a URL the
browser hands us and the server later posts to, so an unchecked one turns this
service into an HTTP client for whoever asks — including at addresses only this
machine can reach. A leading dot matches any host under that domain. Set
ANNRAKSHAK_PUSH_HOSTS to add a self-hosted push service."""

TRUST_PROXY = _flag("ANNRAKSHAK_TRUST_PROXY", False)
"""Whether X-Forwarded-For may be believed. On behind a load balancer or
reverse proxy that sets it; off otherwise, because a client can send that
header itself and a per-IP limit that believes it is no limit at all."""

PUBLIC_DOCS = _flag("ANNRAKSHAK_PUBLIC_DOCS", not PROD)
"""/docs and /openapi.json. On for a laptop and for a judge reading the API;
off in production, where the schema of an authenticated API is not public
business."""

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
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_API_KEYS = list(dict.fromkeys(
    k.strip() for k in [*(os.environ.get("GROQ_API_KEYS") or "").split(","), GROQ_API_KEY or ""] if k.strip()
)) if os.environ.get("ANNRAKSHAK_LLM") != "off" else []
"""Groq keys, used in turn (see llm._chat). The language model reads what a
farmer typed and phrases facts the server computed — it never supplies one.
Without a key Krishi falls back to its own matcher and loses nothing it can
promise."""
GROQ_MODEL = "openai/gpt-oss-20b"
"""Chosen by measurement on 28 questions typed the way farmers actually type
(Hinglish, romanised Marathi, typos): it routed 25 right where Krishi's own
matcher managed 16, and refused all 4 off-topic questions. ~0.5 s on Groq."""
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
LLM_TIMEOUT_S = 10.0
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
AGRO_API_KEY = os.environ.get("AGRO_API_KEY")  # AgroMonitoring: satellite NDVI and soil per field  # optional; Open-Meteo is the keyless fallback
MOSDAC_USERNAME = os.environ.get("MOSDAC_USERNAME")
MOSDAC_PASSWORD = os.environ.get("MOSDAC_PASSWORD")
"""ISRO MOSDAC account (https://mosdac.gov.in/signup/) for INSAT-3DS satellite
rainfall. Optional: without it past rain stays the weather model's estimate."""
MOSDAC_DATASET = os.environ.get("MOSDAC_DATASET", "3SIMG_L2B_HEM")
if len(MOSDAC_DATASET) > 40:  # the width of sat_rain.dataset; a longer id would fail every ingest
    raise SystemExit(f"MOSDAC_DATASET is {len(MOSDAC_DATASET)} characters; the longest this app stores is 40")
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
    "maize_ear_rot": 0.80,
    "maize_gray_leaf_spot": 0.95,
    "maize_turcicum_leaf_blight": 0.90,
    "rice_bacterial_leaf_streak": 0.95,
    "rice_bacterial_panicle_blight": 0.95,
    "rice_blast": 0.95,
    "rice_brown_spot": 0.85,
    "rice_downy_mildew": 0.95,
    "rice_hispa": 0.95,
    "rice_leaf_folder": 0.95,
    "rice_sheath_blight": 0.95,
    "rice_tungro": 0.95,
    "soybean_frogeye_leaf_spot": 0.75,
    "soybean_septoria_brown_spot": 0.95,
    "soybean_yellow_mosaic": 0.95,
}
"""Classes the model names less reliably than the rest must clear a higher
bar before the app advises them — in the photo gate and for a 'strong' view
in the live walk. Measured by ml/tune_gate.py on held-out images (2026-10-17),
choosing the lowest bar reaching 0.95 precision, or, where no bar
reaches it, the bar that does best — those are marked (best) and want more
field photographs rather than more arithmetic:
maize ear rot 0.943 -> 0.971 at 0.80 (recall 1.000);
maize gray leaf spot 0.918 -> 0.949 at 0.95 (recall 0.860) (best);
maize turcicum leaf blight 0.947 -> 0.980 at 0.90 (recall 0.706);
rice bacterial leaf streak 0.913 -> 0.976 at 0.95 (recall 0.953);
rice bacterial panicle blight 0.758 -> 0.852 at 0.95 (recall 0.979) (best);
rice blast 0.807 -> 0.975 at 0.95 (recall 0.561);
rice brown spot 0.931 -> 0.960 at 0.85 (recall 0.535);
rice downy mildew 0.692 -> 0.863 at 0.95 (recall 0.818) (best);
rice hispa 0.844 -> 0.981 at 0.95 (recall 0.681);
rice leaf folder 0.897 -> 0.960 at 0.95 (recall 0.828);
rice sheath blight 0.817 -> 0.913 at 0.95 (recall 0.560) (best);
rice tungro 0.872 -> 0.958 at 0.95 (recall 0.700);
soybean frogeye leaf spot 0.940 -> 0.952 at 0.75 (recall 0.881);
soybean septoria brown spot 0.604 -> 0.875 at 0.95 (recall 0.457) (best);
soybean yellow mosaic 0.861 -> 0.923 at 0.95 (recall 0.585) (best).
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

MAX_ADVISORIES_PER_OFFICER_PER_HOUR = 12
"""An advisory reaches every farm of a crop in a district. A dozen an hour is a
busy outbreak; more than that is a mistake or a script."""

SATELLITE_MAX_AGE_DAYS = 10
"""A greenness drop older than this no longer corroborates today's weather rule:
monsoon cloud can leave the last clear scene a fortnight behind."""

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
DEMO_LOGIN = _flag("ANNRAKSHAK_DEMO_LOGIN", not PROD)
"""'Try the demo' sign-in to the seeded demo farms / a demo expert. Off in production."""
OTP_CHANNEL = "email"
"""Where a one-time code goes when SMS cannot carry it: an officer's code, a
code for an email address, and a farmer's code whenever SMS_BACKEND is off or
the send failed. A farmer who signs in with a mobile number gets their code by
SMS once a provider is configured (app/sms.py); see the SMS section below."""
EXPERT_AUTO_VERIFY = _flag("ANNRAKSHAK_EXPERT_AUTO_VERIFY", not PROD)
"""Whether this build takes an officer's sign-up form at its word: both the
badge and the rank. On, a sign-up is verified and a supervisory post carries a
supervisor's authority, which is what lets a laptop and a judge's walkthrough
have somebody who can route a backlog with nobody around to appoint them. Off,
the post is only the claim the form made and the district office grants both
(POST /api/officials/officers/{id}/verify). Production sets this off; the first
supervisor on a new production database comes from seed.py, since by design no
sign-up can make one."""
# --- Cloudflare Turnstile (the "are you a person" box on sign-in) ---------

TURNSTILE_SITEKEY = os.environ.get("TURNSTILE_SITEKEY", "1x00000000000000000000AA")
TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET", "1x0000000000000000000000000000000AA")
"""Cloudflare's own test pair by default: a real widget, a real verification
call, and nothing refused. Replace both with the site's keys and the same code
starts turning scripts away. Set either to empty to take the box off entirely.

Cloudflare publishes other test keys worth knowing while building this:
  2x00000000000000000000AB / 2x0000000000000000000000000000000AA  always fails
  3x00000000000000000000FF                                        always asks"""

#: Cloudflare's published test secrets. Every one of them is a decision made
#: before the request arrives — always pass, always fail, already spent — so a
#: site running on any of them has a box that asks and an answer that was
#: never in doubt. `start_checks` refuses to let production start on one.
TURNSTILE_TEST_SECRETS = frozenset({
    "1x0000000000000000000000000000000AA",  # always passes
    "2x0000000000000000000000000000000AA",  # always fails
    "3x0000000000000000000000000000000AA",  # token already spent
})

#: How many live field calls one worker will carry at once. Every frame of every
#: call runs the photo model on a worker thread, so beyond a point more callers
#: buy nothing: each frame waits longer, the coaching falls behind what the
#: camera is pointed at, and the calls start timing out together. Better to tell
#: the next caller to try again in a minute than to spoil the calls in progress.
#: Raise it on a machine with more cores, or where the model runs on a GPU.
LIVE_MAX_CALLS = int(os.environ.get("ANNRAKSHAK_LIVE_MAX_CALLS") or 12)

#: How many of those a single account may hold at once. A cap counted only in
#: total is a cap one signed-in caller can fill by itself, which is a cheap way
#: to shut the feature off for everybody else.
LIVE_MAX_PER_CALLER = int(os.environ.get("ANNRAKSHAK_LIVE_MAX_PER_CALLER") or 2)

OTP_DIGITS = 6
OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 30
SESSION_HOURS = 24

#: How long a demo session lives on the server. A demo is somebody looking
#: around, not somebody with a crop in the ground: it should end when they
#: close the tab, and the cookie is written so the browser drops it then. This
#: is the backstop for the browsers that restore tabs and hand the cookie back.
DEMO_SESSION_MINUTES = int(os.environ.get("ANNRAKSHAK_DEMO_SESSION_MINUTES") or 60)
"""A session ends 24 hours after sign-in, however active it was; then sign in again."""
SINGLE_SESSION = True
"""Signing in ends the account's other sessions, so one account is open in one
browser at a time. Demo accounts are exempt: judges share them."""
COOKIE_SECURE = _flag("ANNRAKSHAK_COOKIE_SECURE", PROD)  # on behind HTTPS

SPENT_CODE_DAYS = int(os.environ.get("ANNRAKSHAK_SPENT_CODE_DAYS") or 1)
"""How long a used or expired one-time code is kept before the row goes.

A challenge row holds the address the code was sent to — of anyone who ever
asked for one, including people who never finished signing up. The code is good
for five minutes, so nothing needs the row a day later, and a table that only
ever grows is both a bill and a list of everybody's phone number."""

DEAD_SESSION_DAYS = int(os.environ.get("ANNRAKSHAK_DEAD_SESSION_DAYS") or 30)
"""How long a finished session is kept after it expired or was revoked — long
enough to answer "was this account signed in last week", not forever."""

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

# --- SMS: sign-in codes, alerts and replies for farmers (app/sms.py) -------
#
# Most smallholders have a mobile number and no email, and many have no
# smartphone to run the app on. SMS is the one channel that reaches all of
# them, so it carries the sign-in code for a farmer's mobile number and the
# three moments that matter most: a weather warning, the expert's answer, and
# the day-four question about whether the treatment worked.

SMS_BACKEND = (os.environ.get("SMS_BACKEND") or "off").strip().lower()
"""'off' (the default), 'outbox', 'msg91' or 'twilio'.

  off     no SMS at all: codes go by email, alerts by the app, push and email.
  outbox  writes each message as a file under DATA_DIR/sms-outbox, the way the
          email outbox does. For a laptop; nothing leaves the machine, and
          production refuses to start on it.
  msg91   MSG91's Flow API. Indian SMS legally needs a DLT-registered sender ID
          (header) and a DLT-registered template for every message, so each
          kind of message names its template id below.
  twilio  Twilio's Messages API, for a deployment outside India or a trial.

Off by default rather than outbox, unlike email, because a farmer who signs in
with a mobile number on a laptop would otherwise have their code written to a
file nobody is looking at."""
SMS_BACKENDS = ("off", "outbox", "msg91", "twilio")

SMS_SENDER_ID = os.environ.get("SMS_SENDER_ID", "").strip()
"""The six-letter DLT header the farmer sees as the sender (e.g. ANRKSK)."""

MSG91_AUTH_KEY = os.environ.get("MSG91_AUTH_KEY", "").strip()
MSG91_FLOW_URL = "https://control.msg91.com/api/v5/flow"
MSG91_TEMPLATES = {
    "otp": os.environ.get("MSG91_TEMPLATE_OTP", "").strip(),
    "warning": os.environ.get("MSG91_TEMPLATE_WARNING", "").strip(),
    "verdict": os.environ.get("MSG91_TEMPLATE_VERDICT", "").strip(),
    "followup": os.environ.get("MSG91_TEMPLATE_FOLLOWUP", "").strip(),
    "reply": os.environ.get("MSG91_TEMPLATE_REPLY", "").strip(),
}
"""One MSG91 Flow template per kind of message, each tied to a DLT template.

The message is written here, in the farmer's language, and handed to the
template as variables: `text` (the whole message), `link` (the app link, when
there is one) and, for the code, `otp` and `mins`. The template registered on
DLT decides which of them it shows. A message that does not match its
registered template is dropped by the operator, not by us, so these are
checked at start-up rather than discovered by a farmer who never got a code."""

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM = os.environ.get("TWILIO_FROM", "").strip()
"""A Twilio number in E.164 (+1...) or a Messaging Service SID (MG...)."""

SMS_INBOUND_SECRET = os.environ.get("SMS_INBOUND_SECRET", "").strip()
"""The shared secret a provider's inbound callback must carry: as the
X-AnnRakshak-Secret header, or — for a provider that cannot send headers — as
the callback URL's last segment, /api/sms/inbound/<secret>. Never as a query
parameter (?key=), which access logs write down and which is refused.
Twilio's callbacks are checked by their own signature (TWILIO_AUTH_TOKEN)
instead. Without either, /api/sms/inbound refuses everything, and the
follow-up SMS asks the farmer to answer in the app rather than inviting a
reply nobody will read."""

SMS_TIMEOUT_S = 8.0
"""A provider that has not answered in this long has not sent the message.
Short, because a sign-in code is waited for by a person holding a phone."""

SMS_MAX_PARTS = 2
"""Longest message, in SMS segments. One segment is 160 Latin characters or 70
in an Indian script; a farmer's alert is trimmed to fit two, because three is a
message that arrives in pieces on an old handset and costs three times over."""

SMS_MAX_PER_NUMBER_PER_HOUR = 8
"""Every message to one number, of every kind, in an hour. The backstop under
every other limit: whatever goes wrong upstream — a loop, a retry storm, a
stranger texting the inbound number over and over — one phone is never
flooded and the bill never runs away."""

MAX_ALERT_SMS_PER_FARM_PER_DAY = 3
"""Alert messages (warnings, verdicts, follow-up questions) to one field in a
day. Each costs money and each interrupts somebody; three is a bad day."""

SMS_RETRIES = 3
"""Failed attempts at one message before it is given up on. A provider that is
down for an hour should not lose a warning; one that refuses a message for
good should not be asked every half hour for ever."""

FOLLOWUP_DUE_DAYS = 4
CASE_ETA_MINUTES_PER_POSITION = 20

# --- How long one officer may hold a case ---------------------------------

CASE_RESPONSE_HOURS = 8
"""The clock on one desk. The district's promise to the farmer is 24 hours
(office.SLA_HOURS); this is the share of it any one officer gets before the
case moves on by itself. Three desks still fit inside the promise, which is
where MAX_CASE_HANDOVERS comes from."""

MAX_CASE_HANDOVERS = 3
"""After this many desks have let the clock run out, the case stops being
passed around and waits for a supervisor. A case nobody will answer is a
staffing problem, and circulating it forever hides that."""

assert CASE_RESPONSE_HOURS * MAX_CASE_HANDOVERS <= 24, \
    "a case must not be able to outlive the district's own 24-hour promise"


# --------------------------------------------------------------------------
# What production must not start without
# --------------------------------------------------------------------------

def start_checks() -> list[str]:
    """Everything that is fine on a laptop and wrong in front of farmers.

    Called from the app's lifespan. A laptop gets warnings it can ignore; a
    process that says it is production refuses to start, because every item
    here is something a farmer or an officer would pay for: a stranger signing
    in as a demo officer and reading real cases, a session cookie travelling
    over plain HTTP, a database that disappears with the container.
    """
    problems = []
    if DEMO_LOGIN:
        problems.append("ANNRAKSHAK_DEMO_LOGIN is on: anyone can sign in as a demo farmer or officer")
    if EXPERT_AUTO_VERIFY:
        problems.append("ANNRAKSHAK_EXPERT_AUTO_VERIFY is on: an officer verifies themselves, takes a "
                        "supervisor's rank from their own sign-up form, and may read any farmer's case")
    if not COOKIE_SECURE:
        problems.append("ANNRAKSHAK_COOKIE_SECURE is off: the session cookie will travel over plain HTTP")
    if DB_URL.startswith("sqlite"):
        problems.append("the database is SQLite: set ANNRAKSHAK_DB_URL to Postgres for more than one worker")
    if PUBLIC_APP_URL.startswith("http://localhost"):
        problems.append("ANNRAKSHAK_PUBLIC_URL is still localhost: links in emails and notifications "
                        "will not reach anyone")
    if EMAIL_BACKEND == "outbox":
        problems.append("EMAIL_BACKEND is 'outbox': sign-in codes are written to a file, not sent")
    if TURNSTILE_SECRET in TURNSTILE_TEST_SECRETS:
        # The quiet one. Leaving the box off is a decision somebody made;
        # leaving Cloudflare's test secret in place looks exactly like having
        # it on — a real widget, a real round trip to Cloudflare, a real tick
        # — while the answer was settled before anyone asked. Sign-up is where
        # the officer accounts are made, so an open door here is an open door
        # to the district's cases.
        problems.append("TURNSTILE_SECRET is one of Cloudflare's test keys: the box on sign-in "
                        "is shown and answered but refuses nobody")
    problems += sms_problems()
    return problems


def sms_problems() -> list[str]:
    """What is wrong with the SMS settings, if anything.

    'off' is a decision and says nothing. Everything else here is a farmer
    waiting for a code that is never coming: an outbox file, a provider with
    no key, or an Indian provider with no DLT template for a kind of message,
    which the operator drops without telling anyone."""
    if SMS_BACKEND == "off":
        return []
    if SMS_BACKEND not in SMS_BACKENDS:
        return [f"SMS_BACKEND is {SMS_BACKEND!r}: it must be one of {', '.join(SMS_BACKENDS)}"]
    if SMS_BACKEND == "outbox":
        return ["SMS_BACKEND is 'outbox': sign-in codes and alerts by SMS are written to a file, not sent"]
    missing: list[str] = []
    if SMS_BACKEND == "msg91":
        if not MSG91_AUTH_KEY:
            missing.append("MSG91_AUTH_KEY")
        if not SMS_SENDER_ID:
            missing.append("SMS_SENDER_ID")
        missing += [f"MSG91_TEMPLATE_{kind.upper()}" for kind, tid in MSG91_TEMPLATES.items() if not tid]
    elif SMS_BACKEND == "twilio":
        missing += [name for name, value in (("TWILIO_ACCOUNT_SID", TWILIO_ACCOUNT_SID),
                                             ("TWILIO_AUTH_TOKEN", TWILIO_AUTH_TOKEN),
                                             ("TWILIO_FROM", TWILIO_FROM)) if not value]
    if missing:
        return [f"SMS_BACKEND is {SMS_BACKEND!r} but {', '.join(missing)} "
                f"{'is' if len(missing) == 1 else 'are'} not set: those messages would never be sent"]
    return []
