# AnnRakshak

**Early detection and management of crop diseases and pest infestations.**
Smart India Hackathon 2026 · PS 26131 · Government of Maharashtra.

A farmer photographs a sick plant or gets a "go look here" alert. AnnRakshak
either gives safe, cited advice in Marathi/Hindi, asks one field question when
it is torn between two diseases, or sends the case to a KVK expert — it never
guesses. Every expert verdict updates the farmer, warns nearby farms, and feeds
the officials' surveillance dashboard.

## What's built — mapped to the problem statement

| PS asks for | Where it lives |
|---|---|
| Image-based symptom identification | `ml/train.py` → EfficientNetV2-S / DenseNet201 on the ICAR rice & maize set; `/api/farms/{id}/diagnose` |
| Real-time field scouting | **Live field check** (`/app/live`): a video call with the AI over a WebSocket — it tells the farmer where to point the camera (field, plant, leaf top and underside, base, a second spot), coaches bad frames, and reports only problems seen in two or more separate close-ups, with weather now (OpenWeather), soil pH (sensor → Soil Health Card → SoilGrids), modelled soil moisture, and the forecast risks with prevention. Nothing is recorded except evidence photos of a problem. |
| Pest-trap or sensor inputs | Trap counts vs ICAR-CICR action levels, field-sensor readings override the district forecast (`/traps`, `/sensor`) |
| Weather-based risk forecasting | `backend/app/engine/risk.py` — Open-Meteo window + crop stage + farm history + IMD rainfall normals |
| Geospatial hotspot mapping | Officials' map: confirmed / awaiting-expert / AI-advised cases, 5 km spread radius, active risk alerts |
| Expert validation | `/expert` console: pre-packed case bundles, confirm/correct, lab referral, 3-minute review timer |
| Multilingual advisories | Eleven languages, following the farmer's saved choice: Marathi, Hindi, English (hand-authored) + Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi, Odia (machine translated once with AI4Bharat IndicTrans2 / Sarvam-Translate, placeholders checked, pending native review). Sarvam AI voice in each |
| Weather-based alerts in real time | Hour-by-hour weather screen (temperature, humidity, rain and its chance, wind, gusts, direction, UV, cloud, visibility, pressure, dew point, soil, ET₀) and 15 weather→action rules (lightning, heavy rain, gusts, frost, heat at flowering, fungal weather, spray window, irrigation by FAO-56 water balance…) — delivered in the app instantly, as phone notifications and by email |
| Crop health from space | Satellite greenness (NDVI, Sentinel-2/Landsat 8) and soil moisture per field; a greenness drop becomes an alert |
| Farmer demand signal | 262,778 Kisan Call Centre calls → when and where Maharashtra's farmers ask about each pest |
| IPM + safe input usage | Advice ladder is cultural → biological → chemical (enforced at load and at composition); veto-only spray check |
| Referral to extension / labs | Escalation queue with ETA, lab-referral flag, Kisan Call Centre one-tap call |
| Follow-up monitoring | Day-4 check-in; "got worse" re-escalates automatically |
| Learns from field confirmations | Capped per-district prior + confirmed-vs-corrected field accuracy (not retraining — stated as such) |
| Dashboards for officials | `/officer`: KPIs, gate breakdown, risk outlook, district table, IMD rainfall vs normal, MoSPI pesticide baseline, model card |
| Help inside the app | **Krishi**, always in the bottom-right corner of the farmer app and the sign-in screens: 47 authored help topics covering every screen (en/hi/mr, the other eight from the translation memory) plus 7 live answers from the farmer's own field — can I spray now, will it rain, should I water, what's due today, which pests are coming, what did the expert say. Understands English, Hindi, Marathi and romanised Hinglish; speaks and listens; never makes an answer up and never names a pesticide (`backend/app/krishi.py`, `backend/kb/krishi.json`) |
| Two roles, signed in | Farmers and experts (KVK scientists, agriculture officers, agronomists) sign up with different questions — a farmer's village, GPS field location, crop, sowing date, area, water source and Soil Health Card pH set up their advice; an expert's designation, organisation, staff ID, qualification, experience, districts, crops, specialities and languages decide which cases reach them. One-time codes by email (SMS when a gateway is added), hashed; HttpOnly sessions; every farm, case and dashboard call checks who is asking (`backend/app/auth.py`) |

## Principles that are enforced in code

- **Never a confident wrong answer.** One gate (`engine/gate.py`) returns exactly one of advise / clarify / escalate / retake. Tests cover every band.
- **Uncertainty is shown.** The farmer sees the confidence against the gate's own thresholds and the alternatives.
- **Chemical last.** The knowledge base refuses to load a ladder that isn't cultural → biological → chemical.
- **Veto, never endorse.** The spray check has no vocabulary for "safe".
- **Every alert carries a task.** The database refuses an alert without inspection tasks.
- **Labelled stub.** Without a trained model the API says `is_stub: true` and the app shows a banner.
- **Your farm is yours.** A farmer sees only their own fields; the expert console and officials' dashboard need an expert account; an expert's verdict carries their signed-in name, not a typed one.

## The model, measured

Held-out ICAR test set (126 photos never seen in training, duplicates removed before splitting). Full report: `ml/reports/MODEL_REPORT.md`.

| Method | Test accuracy | Macro-F1 |
|---|---|---|
| DenseNet201 + ANN head, frozen (paper 2's approach) | 81.7% | 0.818 |
| EfficientNetV2-S + ANN head, frozen | 82.5% | 0.823 |
| MobileNetV3 + ANN head, frozen | 79.4% | 0.791 |
| **EfficientNetV2-S fine-tuned (paper 1's approach) — deployed** | **89.7%** | **0.896** |

Deployed now: **v3** (`icar+extra-efficientnet_v2_s-warmstart`) — continual learning from the model above adds rice blast (leaf and neck) and maize common rust; ICAR test 88.9%, and lab-trained classes must clear their own higher gate (0.90).

**End to end, as a farmer uses it** (`ml/live_eval.py` → `ml/reports/LIVE_EVAL.md`; real API, real gate, held-out images only):

| | Result |
|---|---|
| Photo diagnosis, 469 held-out photos | advised 84%, **right on 97.5%** of those; the rest get one field question or go to an expert |
| Live video call, one full walk per class (20 classes) | **20/20 right, 0 wrong**; look-alikes and minority readings go to the expert as "possible" |

Calibration error 0.134 → 0.055 after temperature scaling. ~50 photos per class — treat per-class numbers as indicative; field accuracy is tracked separately from expert verdicts.

## Layout

```
backend/            FastAPI app (port 8010)
  app/engine/       gate, doubt doctor, advisory, risk, weather, prior, vision, label check
  app/routers/      farmer, expert, officials APIs
  kb/               knowledge base: crops, 28 targets, advisories, cues, risk rules, pesticides,
                    IMD rainfall normals, MoSPI pesticide baseline
  tests/            203 tests for the guarantees above
  seed.py           demo farms
  demo_story.py     plays a history through the real API on held-out ICAR photos
frontend/landing/   React app: landing (/), farmer PWA (/app), expert (/expert), officials (/officer)
ml/                 train.py, sample_outcomes.py, reports/ (model report, confusion matrix, Grad-CAM gallery)
data/               ingest.py, DATASETS.md, MANUAL_DOWNLOADS.md (raw data is gitignored)
docs/               INTEGRATIONS.md — external APIs and keys
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

Optional: `.venv/bin/python backend/demo_story.py` to fill the dashboards by running the real flows.

Tests: `cd backend && ../.venv/bin/python -m pytest -q` (always on the deterministic stub, never the paid voice API)

## Data

ICAR crop disease & insect-pest images (rice, maize), a second wave of 10,174 de-duplicated cotton, soybean, maize and rice field photos (`data/ingest_more.py`), IMD rainfall (subdivision monthly 1901–2017, normals, monsoon departures), MoSPI ENVSTATS pesticide consumption, ICAR technology repository (24 entries linked to our pests), live Open-Meteo weather. Provenance, hashes and caveats in `data/DATASETS.md`.
