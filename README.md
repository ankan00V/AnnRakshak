# AnnRakshak

**Early detection and management of crop diseases and pest infestations.**

*Anna*, the harvest. *Rakshak*, its protector.

A farmer photographs a sick plant, or walks their field on a video call with
the AI, or gets a "go and look here" alert before anything is visible. They get
safe, cited advice in their own language, or one field question when the model
is torn between two diseases, or a KVK expert — never a guess. Every expert
verdict updates the farmer, warns the farms around them, and reaches the
district office the same minute.

That last part is the point. A plant-identification app tells one person what
they are holding. This is built so that a disease found in one field becomes a
district's early warning: the farmer's phone is the sensor, the expert is the
check, and the agriculture office is the one who can act at scale.

## 🌾 AnnRakshak — Project Demo

https://github.com/user-attachments/assets/58cca41c-1418-460b-a6ab-f4ede10069d0

## Two apps, one system

| | Who | What it is |
|---|---|---|
| `/app` | Farmer | A PWA in ten languages: diagnose from a photo, walk the field on a live call, hourly weather and spray windows, alerts with tasks, history, their own record to correct. **Krishi** sits in the corner — 55 help topics plus seven answers read from their own field. |
| `/officer` | KVK scientist, agriculture officer, agronomist | One console for the district: today's work, the case queue (review a bundle, confirm / correct / refer to a lab), a hotspot map, advisories to issue, the input indent, model gaps, staff, their own record. **Darpan** answers 15 kinds of question about the district from its own rows — never from the model's imagination. |

There used to be two consoles — a case queue at `/expert` and a dashboard at
`/officer` — and an officer could reach one without ever finding the other.
`/expert` now redirects into the queue where it belongs. One sign-in, one
navigation.

An officer's post decides what they may do: a taluka or district Agriculture
Officer and a KVK scientist supervise — they route a backlog, move another
desk's cases and verify a new colleague. Everyone else advises. The screens
offer only what the signed-in desk can actually do.

## What's built — mapped to the problem statement

| PS asks for | Where it lives |
|---|---|
| Image-based symptom identification | `ml/train.py` → EfficientNetV2-S, **46 classes over 45 advisory targets, all four crops** (rice, maize, cotton, soybean); `/api/farms/{id}/diagnose` |
| Real-time field scouting | **Live field check** (`/app/live`): a video call with the AI over a WebSocket — it tells the farmer where to point the camera (field, plant, leaf top and underside, base, a second spot), coaches bad frames, and reports only problems seen in two or more separate close-ups, with weather now, soil pH (sensor → Soil Health Card → SoilGrids), modelled soil moisture, and forecast risks. Nothing is recorded except evidence photos of a problem. |
| Pest-trap or sensor inputs | Trap counts vs ICAR-CICR action levels; field-sensor readings override the district forecast (`/traps`, `/sensor`) |
| Weather-based risk forecasting | `engine/risk.py` — Open-Meteo window + crop stage + farm history + IMD rainfall normals |
| When the crop will actually be ready | `engine/phenology.py` — growing-degree-days from this field's own temperatures, not a flat "rice is 160 days". Observed (the satellite saw the canopy go) beats thermal beats calendar, and a thermal guess is clamped to the crop calendar's range |
| Geospatial hotspot mapping | Officials' map: confirmed / awaiting-expert / AI-advised cases, 5 km spread radius, active risk alerts |
| Expert validation | `/officer/queue`: pre-packed case bundles with Grad-CAM and the farm's history, confirm / correct / refer to a lab, a three-minute timer. Cases route by district, speciality and current load |
| Multilingual advisories | Ten languages, following the farmer's saved choice: Marathi, Hindi, English (hand-authored) + Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi (machine translated once with AI4Bharat IndicTrans2 / Sarvam-Translate, placeholders checked, pending native review). Voice in each: Bhashini (MeitY), Sarvam as fallback |
| Weather-based alerts in real time | Hour-by-hour weather and **15 weather→action rules** (lightning, heavy rain, gusts, frost, heat at flowering, fungal weather, spray window, irrigation by FAO-56 water balance…) — in the app instantly, as phone notifications and by email |
| Crop health from space | Satellite greenness (NDVI, Sentinel-2/Landsat 8) and soil moisture per field; a greenness drop becomes an alert, and a canopy collapse ends the season |
| Farmer demand signal | 262,778 Kisan Call Centre plant-protection calls from Maharashtra, 2010–2025 (cotton 182,376 · soybean 54,675 · maize 17,748 · rice 7,979), 135,342 of them matched to a pest group — when and where farmers actually ask about each one |
| IPM + safe input usage | Advice ladder is cultural → biological → chemical, enforced at load and at composition; veto-only spray check |
| Referral to extension / labs | Escalation queue with ETA, lab-referral flag, Kisan Call Centre one-tap call |
| Follow-up monitoring | Day-4 check-in; "got worse" re-escalates automatically |
| Learns from field confirmations | Capped per-district prior + confirmed-vs-corrected field accuracy (not retraining — stated as such) |
| Dashboards for officials | `/officer`: seven tabs plus Darpan — Today, Queue, Map, Advisories, Inputs, Model & gaps, and Officers (supervisors only). KPIs, gate breakdown, risk outlook, district table, IMD rainfall vs normal, MoSPI pesticide baseline, input indent, model card |
| Linking a diagnosis to the wider world | 43 of 48 knowledge-base targets carry their **EPPO code** — the identifier that survives a scientific name changing, and what links a verdict to pesticide registrations. The five without one have no single organism to name |
| Help inside the app | **Krishi** for farmers (55 authored topics, 7 live answers from their own field, understands English/Hindi/Marathi/Hinglish, speaks and listens, never invents and never names a pesticide) and **Darpan** for officers (15 intents, answered only from the district's own rows) |
| Two roles, signed in | Farmers and experts sign up with different questions — a farmer's village, GPS field location, crop, sowing date, area, water source and Soil Health Card pH set up their advice; an expert's designation, organisation, staff ID, qualification, experience, districts, crops, specialities and languages decide which cases reach them, and their post decides their authority. One-time codes by email (hashed), HttpOnly sessions, every call checks who is asking (`app/auth.py`) |

## Principles that are enforced in code

- **Never a confident wrong answer.** One gate (`engine/gate.py`) returns exactly one of advise / clarify / escalate / retake. Tests cover every band.
- **Uncertainty is shown.** The farmer sees the confidence against the gate's own thresholds, and the alternatives.
- **Chemical last.** The knowledge base refuses to load a ladder that isn't cultural → biological → chemical.
- **Veto, never endorse.** The spray check has no vocabulary for "safe".
- **Every alert carries a task.** The database refuses an alert without inspection tasks.
- **Labelled stub.** Without a trained model the API says `is_stub: true` and the app shows a banner.
- **Your farm is yours.** A farmer sees only their own fields; an expert's verdict carries their signed-in name, not a typed one.
- **A checkpoint the database cannot record is refused at load**, rather than failing one farmer's photo at a time — a model's name and labels both grow as datasets are folded in, and that has cost a day of diagnoses before.
- **A place name from someone else's database is dropped if it does not fit**, not cut. Half a village's name is a different village.

## The model, measured

Held-out ICAR test set (126 photos never seen in training, duplicates removed
before splitting). Full report: `ml/reports/MODEL_REPORT.md`.

| Method | Test accuracy | Macro-F1 |
|---|---|---|
| DenseNet201 + ANN head, frozen (paper 2's approach) | 81.7% | 0.818 |
| EfficientNetV2-S + ANN head, frozen | 82.5% | 0.823 |
| MobileNetV3 + ANN head, frozen | 79.4% | 0.791 |
| **EfficientNetV2-S fine-tuned (paper 1's approach)** | **89.7%** | **0.896** |

Deployed (8 Oct 2026):
`icar+extra+more+paddy+asdid+local+cotton+thin-efficientnet_v2_s-warmstart` —
continual learning from the model above, now **46 classes over 45 advisory
targets across all four crops**. On the same 126 held-out ICAR photos: **88.9%**
top-1, macro-F1 0.64 (many newer classes have only a handful of test photos
each, which is what pulls the macro average down). Calibration error
**0.102 → 0.056**. The gate advises on **87.3%** and is **right 97.3%** of those
times; 12.7% come to an expert. All **14 deploy checks** passed, including the
background-swap recall bar each lab-trained class must clear.

**End to end, as a farmer uses it** (`ml/live_eval.py` → `ml/reports/LIVE_EVAL.md`;
real API, real gate, held-out images only; last run 17 Oct 2026):

| | Result |
|---|---|
| Photo diagnosis, 2,329 held-out photos | advised 65%, **right on 96.0%** of those; the rest get one field question, a retake, or an expert |
| — ICAR field photos alone (126) | advised 80%, **right on 98.0%** |
| — the newer lab-sourced classes (2,203) | advised 65%, right on 95.9% |
| Live video call, one full walk per class (47 classes) | **45 right, 2 cautious, 0 wrong** |

**How that number was earned.** The run before it advised on 74% and was right
on 89.4%: the model had grown from 20 classes to 46 and the per-class bars in
`config.TARGET_GATE` had not been measured since. `ml/tune_gate.py` puts all
6,254 held-out images through the deployed model and asks, for each class, the
lowest confidence bar that reaches 0.95 precision and what recall that costs.
Fifteen classes now carry a bar of their own — rice downy mildew went
0.692 → 0.863, rice blast 0.807 → 0.975 — and the file records the numbers
behind every entry. The app advises less often and is right far more of the
time when it does.

~50 photos per class for the ICAR set, fewer for some newer classes — treat
per-class numbers as indicative. Field accuracy is tracked separately, from
expert verdicts.

## Layout

```
backend/            FastAPI app (port 8010)
  app/engine/       gate, doubt doctor, advisory, risk, phenology, weather, agromet,
                    satellite, livescan, assign, prior, vision, model, label check
  app/routers/      auth, farmer, expert, officials, krishi, darpan, live, weather, geo
  app/              erasure (the farmer's half of consent), redecide (re-read the queue
                    when a model ships), notify, watch, office, mosdac, turnstile
  kb/               48 targets with EPPO codes, 48 advisories, 25 cues, 30 pesticides,
                    risk rules, IMD rainfall normals, MoSPI pesticide baseline,
                    ICAR technologies, KCC signals, Krishi's 55 topics
  tests/            519 tests for the guarantees above (7 skip off Postgres)
  seed.py           demo districts, farms and officers
  demo_story.py     plays a history through the real API on held-out ICAR photos
frontend/landing/   React 19 + Vite: landing (/), farmer PWA (/app),
                    district office and case queue (/officer)
ml/                 train.py, tune_gate.py, live_eval.py, build_familiarity.py,
                    composite.py, reports/ (model report, live eval, confusion, Grad-CAM)
data/               ingest_*.py per source, DATASETS.md, MANUAL_DOWNLOADS.md
                    (raw data is gitignored)
docs/               INTEGRATIONS.md, DEMO_SCRIPT.md, SEMESTER_REPORT.md
```

## Run it

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r ml/requirements.txt   # API + training/ingest deps (API alone: backend/requirements.txt)
cp .env.example .env              # add SARVAM_API_KEY for voice
.venv/bin/python data/ingest.py   # needs the datasets in data/raw — see data/DATASETS.md
.venv/bin/python ml/train.py      # ~1 h on an M-series Mac (MPS); writes ml/artifacts/
.venv/bin/python ml/sample_outcomes.py   # tags demo photos with the path the gate takes
.venv/bin/python backend/seed.py --reset
.venv/bin/uvicorn app.main:app --port 8010 --app-dir backend
npm install && npm run dev:landing   # http://localhost:5173
```

Optional: `.venv/bin/python backend/demo_story.py` to fill the dashboards by
running the real flows.

Tests: `cd backend && ../.venv/bin/python -m pytest -q` — always on the
deterministic stub, never the paid voice API.

The suite also runs against a real Postgres, which CI does on every push:

```bash
createdb annrakshak_test
ANNRAKSHAK_TEST_DB_URL=postgresql://localhost/annrakshak_test ../.venv/bin/python -m pytest -q
```

SQLite ignores a declared VARCHAR length and cannot alter a column type, so the
migrations in `app/db.py` never execute under it — and a column too narrow for
real data cannot fail. Both have cost a production bug. The override is refused
unless the database is plainly disposable, because the suite drops every table
it finds.

## What a farmer can do with their own data

Consent at sign-up is half a bargain. The account menu holds the other half:

- **Download everything we hold** — one file: the account, the profile, every
  field, every problem, every photograph, every alert and every email we sent.
- **Delete my account** — the person is erased. Name, phone, email, village,
  the fields' coordinates, the sessions, the push subscriptions, the record of
  our emails, and every photograph, as files on disk and not only rows.

What survives erasure is the disease, with nobody in it: a confirmed case of
bacterial blight in Bhandara in September is a fact about a district, not about
a person. The case keeps its crop, date and district; the farm loses its name,
its village and its precise location (rounded to about 11 km). That is the
anonymisation the DPDP Act contemplates, and it is why the surveillance map
does not develop holes when somebody leaves. The rules are in
`backend/app/erasure.py`, in one place, in words.

## Deploy it

One image serves the browser app and the API from the same origin — a
first-party session cookie, no CORS, and every farmer's photograph fetched with
the viewer's own session.

```bash
cp .env.example .env     # ANNRAKSHAK_PUBLIC_URL, SMTP, GROQ_API_KEY, POSTGRES_PASSWORD
docker compose up --build
```

That is the API, Postgres and Redis. The trained model is mounted from
`ml/artifacts/` rather than baked in — without it the API still starts and
serves the labelled stub, and `/health` says so.

**What production refuses to do.** With `ANNRAKSHAK_ENV=production` the app will
not start while a one-tap demo sign-in is enabled, while an expert can verify
themselves, while the session cookie may travel over plain HTTP, or while
sign-in codes are being written to a file instead of sent
(`config.start_checks`). On a laptop the same list is printed as warnings.

**Scaling past one container.** The background watcher — weather rules, the risk
sweep, push and email — must run in exactly one process, or every farmer gets
each alert twice. Run more API containers with `ANNRAKSHAK_WATCH=off` and leave
it on in one. Redis carries the live updates between them, so an alert raised in
one container reaches a tab held open by another.

**When a new model ships.** Open cases carry the verdict of whatever model was
live when the photo arrived. `python -m app.redecide` re-reads them through the
deployed one — a photo that is not a crop withdraws its case, one still needing
an expert keeps its place with a current reason, and a model that is now
confident changes nothing by itself. Dry run unless asked otherwise.

**Behind a proxy.** Set `ANNRAKSHAK_TRUST_PROXY=on` only when something in front
really does set `X-Forwarded-For`; otherwise that header is whatever the caller
typed and every per-IP limit counts a fiction.

## Data

ICAR crop disease & insect-pest images (rice, maize), a second wave of 10,174
de-duplicated cotton, soybean, maize and rice field photos, and further sources
folded in per crop (`data/ingest_*.py`); IMD rainfall (subdivision monthly
1901–2017, normals, monsoon departures); MoSPI ENVSTATS pesticide consumption;
ICAR technology repository (24 technologies, 7 institutes) linked to our pests;
262,778 Kisan Call Centre plant-protection calls (2010–2025);
live Open-Meteo weather; and INSAT-3DS Hydro-Estimator rainfall from MOSDAC.
Provenance, hashes and caveats in `data/DATASETS.md`.

**Acknowledgement:** satellite rainfall data courtesy of MOSDAC (Meteorological
& Oceanographic Satellite Data Archival Centre), Space Applications Centre,
ISRO — https://mosdac.gov.in.
