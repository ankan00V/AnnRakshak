"""Live field walk: frame quality, guidance, evidence rules and the WebSocket flow."""

import base64
import re
import io
from datetime import date, timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageFilter

from app import live, services
from app.db import Base, SessionLocal, engine
from app.engine import fieldnow
from app.engine.livescan import LiveSession, measure
from app.engine.weather import Day, Window
from app.kb import get_kb
from app.main import app
from app.models import Farm, LiveScan, Problem

kb = get_kb()


def leaf(seed: int, *, blur: float = 0, dark: bool = False, grey: bool = False) -> Image.Image:
    """A sharp, green, textured frame; each seed is a different view."""
    rng = np.random.default_rng(seed)
    base = np.array([128, 128, 128] if grey else [70, 150, 55], dtype=np.float32)
    # large-scale shading (differs per view) + fine texture (makes it sharp)
    coarse = np.asarray(Image.fromarray(rng.uniform(0, 255, (4, 5)).astype(np.uint8)).resize((320, 240),
                                                                                             Image.BICUBIC))
    shade = (coarse.astype(np.float32) - 128)[..., None] * 0.35
    a = np.clip(base + shade + rng.normal(0, 6 if grey else 38, (240, 320, 3)), 0, 255)
    if dark:
        a *= 0.15
    im = Image.fromarray(a.astype(np.uint8))
    return im.filter(ImageFilter.GaussianBlur(blur)) if blur else im


def jpeg(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


# --- frame quality ------------------------------------------------------------

def test_quality_accepts_a_sharp_leaf_and_coaches_the_rest():
    assert measure(leaf(1), "close", None).ok
    assert measure(leaf(1, blur=4), "close", None).hint == "hold_steady"
    assert measure(leaf(1, dark=True), "close", None).hint == "too_dark"
    assert measure(leaf(1, grey=True), "scene", None).hint == "show_crop"


def test_same_view_twice_is_not_a_new_view():
    s = LiveSession(crop="rice", lang="en", can_classify=False)
    first = s.on_frame(leaf(3), b"", None)
    again = s.on_frame(leaf(3), b"", None)
    assert first["counted"] and not again["counted"]
    assert again["quality"]["hint"] == "move_a_little"


# --- evidence rules -------------------------------------------------------------

def walk(s: LiveSession, classify, max_frames=200):
    seed = 100
    while not s.done and seed < 100 + max_frames:
        s.on_frame(leaf(seed), f"f{seed}".encode(), classify)
        seed += 1


def test_two_strong_views_make_a_finding():
    s = LiveSession(crop="rice", lang="en", can_classify=True)
    walk(s, lambda img: [("rice_brown_spot", 0.86), ("rice_healthy", 0.1), ("rice_blast", 0.02)])
    f = s.findings(kb)
    assert [x["target"] for x in f["seen"]] == ["rice_brown_spot"]
    assert f["seen"][0]["strong_views"] >= 2 and not f["possible"]
    assert s.evidence_for("rice_brown_spot")  # evidence frames kept for the problem


def test_one_weak_glimpse_adds_a_confirm_step_and_then_goes_to_expert():
    calls = {"n": 0}

    def classify(img):
        calls["n"] += 1
        if calls["n"] == 3:  # a single sighting, below the gate
            return [("rice_brown_spot", 0.55), ("rice_healthy", 0.4), ("rice_blast", 0.02)]
        return [("rice_healthy", 0.92), ("rice_brown_spot", 0.05), ("rice_blast", 0.01)]

    s = LiveSession(crop="rice", lang="en", can_classify=True)
    walk(s, classify)
    assert any(st.id == "confirm" for st in s.steps)
    f = s.findings(kb)
    assert not f["seen"]
    assert [x["target"] for x in f["possible"]] == ["rice_brown_spot"]


def test_healthy_field_has_no_findings():
    s = LiveSession(crop="maize", lang="hi", can_classify=True)
    walk(s, lambda img: [("maize_healthy", 0.95), ("maize_aphid", 0.03), ("maize_maydis_leaf_blight", 0.01)])
    f = s.findings(kb)
    assert not f["seen"] and not f["possible"] and f["healthy_views"] > 0


def test_other_crop_views_are_counted_not_reported():
    s = LiveSession(crop="rice", lang="en", can_classify=True)
    walk(s, lambda img: [("maize_fall_armyworm", 0.9), ("rice_healthy", 0.05), ("rice_blast", 0.01)])
    f = s.findings(kb)
    assert not f["seen"] and f["other_crop_views"] > 0


def test_competing_problems_trigger_the_doubt_doctor_question():
    flip = {"n": 0}

    def classify(img):
        flip["n"] += 1
        a, b = ("maize_turcicum_leaf_blight", "maize_maydis_leaf_blight")
        return [(a, 0.5), (b, 0.44), ("maize_healthy", 0.03)] if flip["n"] % 2 else \
            [(b, 0.5), (a, 0.44), ("maize_healthy", 0.03)]

    s = LiveSession(crop="maize", lang="en", can_classify=True)
    walk(s, classify)
    cue = s.pending_question(kb)
    assert cue and set(cue["pair"]) == {"maize_turcicum_leaf_blight", "maize_maydis_leaf_blight"}
    s.on_answer(cue["id"], "yes")
    assert s.findings(kb)["seen"][0]["target"] == cue["yes_means"]


# --- the WebSocket session end to end -----------------------------------------

@pytest.fixture()
def client(monkeypatch):
    humid = Window([Day(date.today() - timedelta(6 - i), 92, 23, 30, 6.0) for i in range(7)]
                   + [Day(date.today() + timedelta(i + 1), 93, 23, 29, 8.0) for i in range(3)],
                   "test", None)
    monkeypatch.setattr(services, "fetch_window", lambda lat, lon: humid)
    monkeypatch.setattr(services, "fetch_month_rain", lambda lat, lon: None)
    monkeypatch.setattr(fieldnow, "conditions_now", lambda lat, lon, lang, **kw: {
        "weather": {"temp_c": 28.3, "rh_pct": 79, "rain_mm_1h": 0, "wind_kmh": 5, "text": "clear sky",
                    "station": None, "source": "test", "observed_at": "now"},
        "soil_model": {"moisture_pct_surface": 40.0, "moisture_pct_3_9cm": 42.0, "temp_c_surface": 30.0,
                       "source": "test model"}})
    monkeypatch.setattr(fieldnow, "soilgrids", lambda lat, lon, **kw: {"ph": 7.4, "soc_g_per_kg": 13.3,
                                                                       "source": "test map"})
    monkeypatch.setattr(live.vision, "model_status", lambda: {"is_stub": False, "model_version": "test-model"})
    monkeypatch.setattr(live, "classify", lambda img: [("rice_brown_spot", 0.88), ("rice_healthy", 0.08),
                                                       ("rice_blast", 0.02)])
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:
        with SessionLocal() as db:
            db.add(Farm(farmer_name="t", crop="rice", sowing_date=date.today() - timedelta(days=60),
                        district="Bhandara", lat=21.17, lon=79.65, area_acres=2, lang="mr"))
            db.commit()
        yield c


def test_live_walk_end_to_end(client):
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "mr", "lat": 21.171, "lon": 79.651, "accuracy": 8})
        ready = ws.receive_json()
        assert ready["type"] == "ready" and ready["photo_model"]
        ctx = ready["context"]
        assert ctx["location"]["source"] == "gps" and not ctx["location"]["far_from_farm"]
        assert ctx["soil"]["ph"]["how"] == "estimated" and ctx["weather_now"]["temp_c"] == 28.3
        assert ready["guide"]["step"] == "overview" and ready["guide"]["text"]
        seq, done = 0, False
        while not done and seq < 120:
            ws.send_json({"type": "frame", "seq": seq,
                          "data": base64.b64encode(jpeg(leaf(500 + seq))).decode()})
            while True:
                m = ws.receive_json()
                if m["type"] == "steps_done":
                    done = True
                    break
                if m["type"] == "frame":
                    assert m["seq"] == seq
                    if done:
                        break
                    # the frame reply comes first; steps_done may follow it
                    if not m["guide"]["step"]:
                        continue
                    break
            seq += 1
        assert done
        ws.send_json({"type": "finish"})
        m = ws.receive_json()
        while m["type"] != "summary":
            m = ws.receive_json()
        s = m["summary"]
    assert s["verdict"] == "found"
    assert [x["target"] for x in s["seen"]] == ["rice_brown_spot"]
    assert s["seen"][0]["evidence"] and s["seen"][0]["advisory"]["ladder"]
    assert "सामू" in s["speech"]  # Marathi summary mentions soil pH
    with SessionLocal() as db:
        scan = db.query(LiveScan).one()
        assert scan.verdict == "found" and scan.problem_ids
        p = db.get(Problem, scan.problem_ids[0])
        assert p.target == "rice_brown_spot" and p.diagnoses[0].gate_reason == "LIVE_MULTI_VIEW"
    # The farmer switches to English on the summary screen: same findings, English words.
    en = client.get(f"/api/farms/1/live/{s['scan_id']}?lang=en").json()
    assert en["verdict"] == s["verdict"] and [x["target"] for x in en["seen"]] == ["rice_brown_spot"]
    assert en["seen"][0]["name"].isascii() and en["seen"][0]["name"] != s["seen"][0]["name"]
    assert en["context"]["crop"]["name"].isascii() and en["seen"][0]["advisory"]["ladder"]
    assert [r["target"] for r in en["context"]["risks"]] == [r["target"] for r in s["context"]["risks"]]
    assert not any(re.search("[\u0900-\u097f]", r["reason"]) for r in en["context"]["risks"])  # no Devanagari left
    assert "pH" in en["speech"] and "सामू" not in en["speech"]
    assert client.get(f"/api/farms/2/live/{s['scan_id']}?lang=en").status_code == 404


def test_disconnect_before_finish_saves_nothing(client):
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en"})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "frame", "seq": 0, "data": base64.b64encode(jpeg(leaf(1))).decode()})
        ws.receive_json()
    with SessionLocal() as db:
        assert db.query(LiveScan).count() == 0 and db.query(Problem).count() == 0


def test_bad_frames_are_rejected_without_ending_the_call(client):
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en"})
        ws.receive_json()
        ws.send_json({"type": "frame", "seq": 1, "data": "not base64!!"})
        assert ws.receive_json()["code"] == "BAD_FRAME"
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"


def test_live_context_endpoint(client):
    r = client.get("/api/farms/1/live/context?lang=hi").json()
    assert r["location"]["source"] == "farm" and r["crop"]["name"] and r["risks"]
    assert r["risks"][0]["prevention"]["do"]


def test_tiny_frames_are_rejected_and_an_empty_walk_still_finishes(client):
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en"})
        ws.receive_json()
        ws.send_json({"type": "frame", "seq": 1,
                      "data": base64.b64encode(jpeg(Image.new("RGB", (2, 2), (0, 0, 0)))).decode()})
        assert ws.receive_json()["code"] == "BAD_FRAME"
        ws.send_json({"type": "finish"})
        s = ws.receive_json()["summary"]
    assert s["verdict"] in {"risk", "all_good"} and not s["seen"] and s["speech"]


def test_soil_health_card_ph_beats_the_soil_map_and_a_sensor_beats_both(client):
    body = {"farmer_name": "c", "lang": "en", "crop": "maize", "sowing_date": str(date.today() - timedelta(days=40)),
            "district": "Pune", "lat": 18.52, "lon": 73.85, "area_acres": 1, "soil_ph": 6.4,
            "soil_ph_on": str(date.today())}
    fid = client.post("/api/farms", json=body).json()["id"]
    ph = client.get(f"/api/farms/{fid}/live/context").json()["soil"]["ph"]
    assert ph["how"] == "card" and ph["value"] == 6.4
    client.post(f"/api/farms/{fid}/sensor", json=[{"on": str(date.today()), "soil_ph": 7.1,
                                                    "soil_moisture_pct": 31}])
    soil = client.get(f"/api/farms/{fid}/live/context").json()["soil"]
    assert soil["ph"]["how"] == "measured" and soil["ph"]["value"] == 7.1
    assert soil["moisture"]["how"] == "measured" and soil["moisture"]["value_pct"] == 31


def test_sharpness_of_a_sliver_is_zero_not_nan():
    import math

    from app.engine.livescan import sharpness
    assert sharpness(np.zeros((2, 2))) == 0.0 and not math.isnan(sharpness(np.zeros((1, 50))))


def test_a_minority_reading_goes_to_the_expert_not_to_the_farmer():
    calls = {"n": 0}

    def classify(img):
        calls["n"] += 1
        if calls["n"] in (4, 9):  # two strong misreads in a walk that shows brown spot throughout
            return [("rice_sheath_blight", 0.81), ("rice_brown_spot", 0.15), ("rice_healthy", 0.02)]
        return [("rice_brown_spot", 0.9), ("rice_sheath_blight", 0.06), ("rice_healthy", 0.02)]

    s = LiveSession(crop="rice", lang="en", can_classify=True)
    walk(s, classify)
    f = s.findings(kb)
    assert [x["target"] for x in f["seen"]] == ["rice_brown_spot"]
    other = next(x for x in f["possible"] if x["target"] == "rice_sheath_blight")
    assert other["reason"] == "MINORITY_VIEWS" and other["strong_views"] == 2


def test_a_lab_trained_class_needs_its_own_higher_bar_in_the_live_walk():
    s = LiveSession(crop="rice", lang="en", can_classify=True)
    walk(s, lambda img: [("rice_blast", 0.85), ("rice_brown_spot", 0.1), ("rice_healthy", 0.02)])
    f = s.findings(kb)
    assert not f["seen"] and f["possible"][0]["target"] == "rice_blast"  # 0.85 < blast's 0.90


def test_look_alikes_are_not_both_reported_as_seen():
    calls = {"n": 0}

    def classify(img):
        calls["n"] += 1
        if calls["n"] % 3 == 0:  # a third of close-ups read confidently as blast
            return [("rice_blast", 0.95), ("rice_brown_spot", 0.03), ("rice_healthy", 0.01)]
        return [("rice_brown_spot", 0.92), ("rice_blast", 0.05), ("rice_healthy", 0.01)]

    s = LiveSession(crop="rice", lang="en", can_classify=True)
    walk(s, classify)
    f = s.findings(kb)
    assert [x["target"] for x in f["seen"]] == ["rice_brown_spot"]
    assert next(x for x in f["possible"] if x["target"] == "rice_blast")["reason"] == "LOOKALIKE"


def test_a_frame_the_model_does_not_recognise_as_a_crop_never_counts():
    s = LiveSession(crop="rice", lang="en", can_classify=True)
    while s.steps[s.idx].kind != "close":  # walk to the first close-up step
        s.on_frame(leaf(1000 + s.frames), b"x", lambda img: [])
    need_before = s.steps[s.idx].got
    out = s.on_frame(leaf(4242), b"face", lambda img: [])  # e.g. a person in front of plants
    assert not out["counted"] and out["quality"]["hint"] == "show_crop"
    assert s.steps[s.idx].got == need_before and s.classified == 0


def test_language_switch_mid_call(client):
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "mr", "lat": 21.171, "lon": 79.651})
        ready = ws.receive_json()
        assert re.search("[ऀ-ॿ]", ready["guide"]["text"])
        ws.send_json({"type": "lang", "lang": "en"})
        m = ws.receive_json()
        assert m["type"] == "lang" and m["guide"]["step"] == ready["guide"]["step"]
        assert not re.search("[ऀ-ॿ]", m["guide"]["text"] + m["context"]["crop"]["name"])
