"""Live field walk: frame quality, guidance, evidence rules and the WebSocket flow."""

import base64
import contextlib
import re
import io
import time
from datetime import date, timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageFilter

from app import live, services
from app.db import Base, SessionLocal, engine
from app.engine import fieldnow
from app import config
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


# --- what the call says -------------------------------------------------------

def test_the_call_speaks_every_language_the_app_offers():
    """The walk is spoken aloud, step by step. A language missing from here does
    not fail — tr() quietly falls back to English — so a farmer who chose Tamil
    is talked to in English by the one screen that never stops talking. Nothing
    catches that but this."""
    from app.engine.livescan import HINTS, TEXT
    from app.i18n import LANGS
    from app.notify import FOLLOWUP_TEXT, VERDICT_TEXT
    from app.services import VERDICT_NAMES
    for name, table in (("TEXT", TEXT), ("HINTS", HINTS), ("VERDICT_NAMES", VERDICT_NAMES),
                        # The push notifications are the same problem one step
                        # further out: nobody sees an English fallback land on
                        # a phone, so nothing but this catches a missing one.
                        ("VERDICT_TEXT", VERDICT_TEXT), ("FOLLOWUP_TEXT", FOLLOWUP_TEXT)):
        for key, said in table.items():
            missing = [lg for lg in LANGS if not said.get(lg, "").strip()]
            assert not missing, f"{name}[{key}] does not speak {missing}"


def test_the_confirm_step_keeps_its_placeholder_in_every_language():
    """"I think I see {name}" loses the disease if a translation drops it."""
    from app.engine.livescan import TEXT
    for lg, said in TEXT["confirm"].items():
        assert "{name}" in said, f"confirm[{lg}] lost the disease name"


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


# --- a video the farmer already filmed ------------------------------------------

def test_a_video_is_read_without_asking_for_views_it_cannot_have():
    """The guided walk coaches a camera towards six views. A file is already
    shot, so it gets no steps and no coaching — it is read, and what the
    readings are worth is settled by the same evidence rules."""
    s = LiveSession(crop="rice", lang="en", can_classify=True, mode="video")
    out = s.on_frame(leaf(7), b"f7", lambda img: [("rice_brown_spot", 0.88)])
    assert out["guide"]["step"] is None          # nothing is being asked for
    assert out["guide"]["total"] == 0            # and there is no step to be at
    assert out["quality"]["hint_text"] is None   # a file cannot be coached
    assert out["counted"] and out["guide"]["kept"] == 1
    assert not s.done                            # only the caller ends a video
    s.ended = True
    assert s.done


def test_one_view_held_for_a_long_time_is_still_one_view():
    """The decision this pins: a video gets no easier bar than a walk.

    Thirty seconds on a single diseased leaf feels like far more evidence than
    two photographs and is not — a model that misreads that leaf misreads every
    frame of it identically, so the frames are one sample, not thirty. The
    novelty gate is what keeps the count honest: it measures each frame against
    the last accepted one, so an unchanging view accumulates nothing however
    long it runs, and the answer is an expert rather than a confident name.
    """
    sure = lambda img: [("rice_brown_spot", 0.95), ("rice_healthy", 0.03)]  # noqa: E731
    s = LiveSession(crop="rice", lang="en", can_classify=True, mode="video")
    frame = leaf(11)
    for _ in range(40):                     # the same leaf, over and over
        s.on_frame(frame, b"same", sure)
    s.ended = True

    assert s.kept == 1, "an unchanging view counted more than once"
    f = s.findings(kb)
    assert not f["seen"], "forty frames of one leaf became a confident verdict"
    assert [x["target"] for x in f["possible"]] == ["rice_brown_spot"]
    assert s.why_thin() == "move_a_little", "the farmer is not told to move along the row"


def test_a_video_reaches_the_same_verdict_as_a_walk():
    sure = lambda img: [("rice_brown_spot", 0.86), ("rice_healthy", 0.1), ("rice_blast", 0.02)]  # noqa: E731
    s = LiveSession(crop="rice", lang="en", can_classify=True, mode="video")
    for seed in range(100, 130):
        s.on_frame(leaf(seed), f"f{seed}".encode(), sure)
    s.ended = True
    f = s.findings(kb)
    assert [x["target"] for x in f["seen"]] == ["rice_brown_spot"]
    assert f["seen"][0]["strong_views"] >= 2
    assert s.evidence_for("rice_brown_spot")


def test_a_video_too_thin_to_read_goes_to_an_expert_not_to_a_spray():
    once = [0]

    def classify(img):
        once[0] += 1
        if once[0] == 1:
            return [("rice_brown_spot", 0.55), ("rice_healthy", 0.4)]
        return [("rice_healthy", 0.92), ("rice_brown_spot", 0.05)]

    s = LiveSession(crop="rice", lang="en", can_classify=True, mode="video")
    for seed in range(200, 212):
        s.on_frame(leaf(seed), f"f{seed}".encode(), classify)
    s.ended = True
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


def test_a_view_the_farmer_cannot_get_can_be_skipped(client):
    """Not every field has a leaf you can turn over or a base above the water.
    Coaching towards a picture that does not exist until the session times out
    wastes the walk and ends with nothing."""
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "mr"})
        assert ws.receive_json()["guide"]["step"] == "overview"
        ws.send_json({"type": "skip"})
        m = ws.receive_json()
        assert m["type"] == "guide" and m["advanced"]
        assert m["guide"]["step"] == "plant"


def test_a_dropped_call_can_be_picked_back_up(client):
    """Five minutes into a field on a patchy network, a dropped connection must
    not mean walking it again from the gate."""
    token, step, got = None, None, None
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "mr"})
        ready = ws.receive_json()
        token = ready["resume"]
        assert token and not ready["resumed"]
        for seq in range(2):  # short of the three the first view wants
            ws.send_json({"type": "frame", "seq": seq,
                          "data": base64.b64encode(jpeg(leaf(700 + seq))).decode()})
            m = ws.receive_json()
            step, got = m["guide"]["step"], m["guide"]["got"]
        assert step == "overview" and got == 2, "part-way through the first view"
        # and here the network goes

    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        back = ws.receive_json()
        assert back["type"] == "ready" and back["resumed"]
        assert back["guide"]["step"] == step and back["guide"]["got"] == got


def test_a_resume_token_is_good_once_and_only_for_its_own_field(client):
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "mr"})
        token = ws.receive_json()["resume"]
        ws.send_json({"type": "frame", "seq": 1, "data": base64.b64encode(jpeg(leaf(9))).decode()})
        ws.receive_json()

    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        assert ws.receive_json()["type"] == "ready"
        # Heard on the new line, so "ready" — and the token in it — arrived.
        # (Until then the old token still works: see the test below on a
        # reconnection that drops again at once.)
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"
    # spent: the same token does not open a second call
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        assert ws.receive_json()["code"] == "RESUME_UNKNOWN"


def test_hanging_up_before_saying_anything_is_not_an_error(client):
    """A caller who disconnects while the server is still waiting for their
    opening message leaves none of a call's state behind to clean up."""
    with client.websocket_connect("/api/live/1"):
        pass  # gone before "start"


def test_a_made_up_resume_token_is_refused_without_breaking_the_call(client):
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": "not-a-real-token"})
        assert ws.receive_json()["code"] == "RESUME_UNKNOWN"


def _settles_at(n: int, timeout: float = 2.0) -> int:
    """The handler unwinds on the server's own thread; give it a moment."""
    from app.routers import live as R
    end = time.monotonic() + timeout
    while R._in_progress() != n and time.monotonic() < end:
        time.sleep(0.02)
    return R._in_progress()


def test_a_socket_that_says_nothing_takes_no_place_in_the_queue(client, monkeypatch):
    """The cap on calls in flight is only worth having if it cannot be filled by
    sockets that never become calls. Opening a connection and going quiet is the
    cheapest attack there is."""
    from app.routers import live as R

    monkeypatch.setattr(R, "OPENING_SECONDS", 0.2)
    with contextlib.suppress(Exception), client.websocket_connect("/api/live/1"):
        time.sleep(0.5)
        assert R._in_progress() == 0
    assert _settles_at(0) == 0
    # and the next caller is not turned away because of it
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en"})
        assert ws.receive_json()["type"] == "ready"


def test_one_caller_cannot_take_every_place(client, monkeypatch):
    """A cap counted only in total is a cap one signed-in account can fill by
    itself, which shuts the feature off for everybody else."""
    monkeypatch.setattr(config, "LIVE_MAX_PER_CALLER", 1)
    with client.websocket_connect("/api/live/1") as first:
        first.send_json({"type": "start", "lang": "en"})
        assert first.receive_json()["type"] == "ready"
        with client.websocket_connect("/api/live/1") as second:
            second.send_json({"type": "start", "lang": "en"})
            assert second.receive_json()["code"] == "TOO_BUSY"


def test_a_call_gone_quiet_is_let_go_but_not_thrown_away(client, monkeypatch):
    """A phone that goes flat mid-walk must not hold its place for ever — and
    must not lose the walk either."""
    from app.routers import live as R

    monkeypatch.setattr(R, "IDLE_SECONDS", 0.3)
    with contextlib.suppress(Exception), client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en"})
        token = ws.receive_json()["resume"]
        ws.send_json({"type": "frame", "seq": 1, "data": base64.b64encode(jpeg(leaf(31))).decode()})
        ws.receive_json()
        time.sleep(1.0)   # the phone says nothing at all
    assert _settles_at(0) == 0, "a silent call kept its place"

    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        assert ws.receive_json()["resumed"], "the walk should have been held, not binned"


def test_a_call_in_progress_holds_no_database_connection(client):
    """The pool holds fifteen connections and a call lasts minutes. If a walk
    kept one for its whole length, fifteen farmers walking at once would stop
    every other request in the application — and an open transaction that long
    is cut from under the call by PgBouncer anyway. The frames need no database,
    so between the context and the save there must be nothing checked out."""
    from app.db import engine

    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "mr"})
        assert ws.receive_json()["type"] == "ready"
        # The context has been built and the walk is under way.
        assert engine.pool.checkedout() == 0
        ws.send_json({"type": "frame", "seq": 1, "data": base64.b64encode(jpeg(leaf(1))).decode()})
        assert ws.receive_json()["type"] == "frame"
        assert engine.pool.checkedout() == 0, "a frame left a connection checked out"


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


def test_a_walk_that_saw_no_plant_says_so_and_never_calls_the_crop_healthy(client):
    """This test used to assert the bug: a walk sent only an unusable frame and
    was expected to finish "risk" or "all_good" — the screen then read "Healthy
    now, but watch out" about plants the camera never saw."""
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en"})
        ws.receive_json()
        ws.send_json({"type": "frame", "seq": 1,
                      "data": base64.b64encode(jpeg(Image.new("RGB", (2, 2), (0, 0, 0)))).decode()})
        assert ws.receive_json()["code"] == "BAD_FRAME"
        ws.send_json({"type": "finish"})
        s = ws.receive_json()["summary"]
    assert s["verdict"] == "unclear" and not s["seen"]
    assert "could not see your plants clearly" in s["speech"] and "look healthy" not in s["speech"]


@pytest.mark.parametrize(("seen", "possible", "model", "healthy", "risks", "want"), [
    (True, False, True, 0, True, "found"),
    (False, True, True, 0, False, "check"),
    (False, False, False, 5, True, "no_model"),     # cotton/soybean: never "healthy"
    (False, False, True, 0, True, "unclear"),       # nothing recognised
    (False, False, True, 1, False, "unclear"),      # one confident view is not enough
    (False, False, True, 2, True, "risk"),
    (False, False, True, 3, False, "all_good"),
])
def test_the_walk_only_claims_what_the_camera_saw(seen, possible, model, healthy, risks, want):
    from app.live import walk_verdict
    assert walk_verdict(seen, possible, model, healthy, risks) == want


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

    # "Strong" is each class's own bar, so take both from config rather than
    # from two numbers that were true of an older table.
    wrong = min(round(config.gate_for("rice_sheath_blight") + 0.02, 2), 0.97)
    right = min(round(config.gate_for("rice_brown_spot") + 0.02, 2), 0.97)

    def classify(img):
        calls["n"] += 1
        if calls["n"] in (4, 9):  # two strong misreads in a walk that shows brown spot throughout
            return [("rice_sheath_blight", wrong), ("rice_brown_spot", 0.02), ("rice_healthy", 0.01)]
        return [("rice_brown_spot", right), ("rice_sheath_blight", 0.02), ("rice_healthy", 0.01)]

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


# --- how the looking itself went ----------------------------------------------

def test_a_video_remembers_where_it_saw_what_it_saw():
    """A verdict off a video is a claim about particular seconds of it. The
    farmer should be able to go back to those seconds and look at the leaf —
    and a year on, the record should still say how much of the file could be
    read, not only what was concluded from it."""
    readings = iter([[("rice_healthy", 0.93)], [("rice_brown_spot", 0.9)], [("rice_brown_spot", 0.86)]])
    s = LiveSession(crop="rice", lang="en", can_classify=True, mode="video")
    s.on_frame(leaf(1, dark=True), b"dark", lambda img: next(readings), at=0.0)   # passed over
    assert s.on_frame(leaf(2), b"a", lambda img: next(readings), at=1.0)["mark"] == "h"
    assert s.on_frame(leaf(3), b"b", lambda img: next(readings), at=7.5)["mark"] == "p"
    assert s.on_frame(leaf(4), b"c", lambda img: next(readings), at=19.0)["mark"] == "p"
    s.ended = True

    f = s.findings(kb)
    assert f["seen"][0]["moments"] == [7.5, 19.0]
    r = f["reading"]
    assert r["mode"] == "video" and (r["read"], r["clear"], r["kept"]) == (4, 3, 3)
    assert r["marks"] == [[0.0, "x"], [1.0, "h"], [7.5, "p"], [19.0, "p"]]
    assert r["passed_over"] == {"too_dark": 1} and r["why_thin"] is None


def test_a_walk_has_no_seconds_to_point_at():
    s = LiveSession(crop="rice", lang="en", can_classify=True)
    s.skip()
    r = s.findings(kb)["reading"]
    assert r == {"mode": "walk", "skipped": ["overview"], "other_crop": None}


def test_footage_of_another_crop_is_called_what_it_is():
    """Two fields, the wrong one picked — or a field still registered under last
    season's crop. Every reading is rightly set aside as another crop, and the
    farmer used to be told the camera could not see their plants: false, and it
    sent them out to film the same maize again."""
    maize = lambda img: [("maize_healthy", 0.9), ("maize_rust", 0.05)]  # noqa: E731
    s = LiveSession(crop="rice", lang="en", can_classify=True, mode="video")
    for seed in range(300, 306):
        s.on_frame(leaf(seed), f"m{seed}".encode(), maize, at=float(seed - 300))
    s.ended = True
    assert s.other_crop_seen() == {"crop": "maize", "views": 6}
    assert s.why_thin() == "other_crop", "plenty of clear frames, all of the wrong crop"
    f = s.findings(kb)
    assert not f["seen"] and not f["possible"]
    assert {m[1] for m in f["reading"]["marks"]} == {"o"}

    view = live.reading_view(kb, f["reading"], "rice", "hi")
    assert "मक्का" in view["other_crop"]["text"] and "धान" in view["other_crop"]["text"]


def test_one_misread_leaf_is_not_another_crop():
    readings = iter([[("maize_rust", 0.6)]] + [[("rice_healthy", 0.92)]] * 5)
    s = LiveSession(crop="rice", lang="en", can_classify=True, mode="video")
    for seed in range(320, 326):
        s.on_frame(leaf(seed), b"x", lambda img: next(readings))
    assert s.other_crop == 1 and s.other_crop_seen() is None and s.why_thin() is None


# --- the socket, held to the same things --------------------------------------

def frame_msg(seq: int, seed: int, **more) -> dict:
    return {"type": "frame", "seq": seq, "data": base64.b64encode(jpeg(leaf(seed))).decode()} | more


def read_video(ws, seeds, step: float = 1.0) -> dict:
    """Send frames the way the upload screen does and return the last reply."""
    m = {}
    for i, seed in enumerate(seeds):
        ws.send_json(frame_msg(i, seed, at=i * step))
        m = ws.receive_json()
        assert m["type"] == "frame", m
    return m


def summary_of(ws) -> dict:
    m = ws.receive_json()
    while m["type"] != "summary":
        assert m["type"] != "error", f"asked for the result and was refused: {m}"
        m = ws.receive_json()
    return m["summary"]


def test_a_video_end_to_end_keeps_its_reading(client):
    """The upload route through the real socket: read, ended, saved — and the
    saved record says it was a video, how much of it was readable and where the
    problem was seen, in whichever language it is opened in later."""
    with client.websocket_connect("/api/live/1") as ws:
        # A laptop's idea of where it is must not move the field: the weather
        # and the "you are far from your field" line are about the crop.
        ws.send_json({"type": "start", "lang": "mr", "mode": "video", "lat": 12.97, "lon": 77.59, "accuracy": 30})
        ready = ws.receive_json()
        assert ready["context"]["location"]["source"] == "farm"
        assert not ready["context"]["location"]["far_from_farm"]
        last = read_video(ws, range(800, 808), step=2.0)
        assert last["mark"] == "p" and last["guide"]["kept"] == 8
        ws.send_json({"type": "end_of_video"})
        assert ws.receive_json()["type"] == "steps_done"
        ws.send_json({"type": "finish"})
        s = summary_of(ws)

    assert s["verdict"] == "found" and s["reading"]["mode"] == "video"
    assert s["reading"]["kept"] == 8 and len(s["reading"]["marks"]) == 8
    assert s["seen"][0]["moments"][:3] == [0.0, 2.0, 4.0]
    with SessionLocal() as db:
        scan = db.query(LiveScan).one()
        assert scan.findings["reading"]["mode"] == "video"
        assert scan.location_source == "farm"
    en = client.get(f"/api/farms/1/live/{s['scan_id']}?lang=en").json()
    assert en["reading"] == s["reading"], "the reading changed when the language did"
    assert en["seen"][0]["moments"] == s["seen"][0]["moments"]


def test_a_thin_video_says_why_in_the_saved_summary(client, monkeypatch):
    """Why a video gave nothing used to live only in the browser's memory of
    the call: reload, or switch language, and the explanation was gone and the
    generic "hold the phone close to a leaf" came back in its place."""
    monkeypatch.setattr(live, "classify", lambda img: [])     # nothing the model knows as a crop
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        ws.receive_json()
        read_video(ws, range(820, 826))
        ws.send_json({"type": "end_of_video"})
        ws.receive_json()
        ws.send_json({"type": "finish"})
        s = summary_of(ws)
    assert s["verdict"] == "unclear" and s["reading"]["why_thin"] == "not_crop"
    assert "video" in s["speech"] and "hold the phone" not in s["speech"]
    again = client.get(f"/api/farms/1/live/{s['scan_id']}?lang=hi").json()
    assert again["reading"]["why_thin"] == "not_crop"


def test_a_video_dropped_mid_read_is_picked_back_up(client):
    """Three minutes of footage read to the last ten seconds, and the wifi
    blinks. Only a walk used to be held; a video was thrown away."""
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = ws.receive_json()["resume"]
        read_video(ws, range(840, 844))
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        back = ws.receive_json()
        assert back["resumed"] and back["guide"]["read"] == 4 and back["guide"]["kept"] == 4
        ws.send_json(frame_msg(9, 850, at=9.0))
        assert ws.receive_json()["guide"]["kept"] == 5
        ws.send_json({"type": "end_of_video"})
        assert ws.receive_json()["type"] == "steps_done"
        ws.send_json({"type": "finish"})
        assert summary_of(ws)["reading"]["read"] == 5


def test_a_message_that_is_not_a_message_does_not_end_the_call(client):
    """Text that is not JSON raised straight out of the handler, and a JSON list
    has no .get — either one ended the call on an unhandled error, which also
    skipped the parking, so the walk went with it."""
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en"})
        ws.receive_json()
        ws.send_text("{not json")
        assert ws.receive_json()["code"] == "BAD_MESSAGE"
        ws.send_json(["frame", 1])
        assert ws.receive_json()["code"] == "BAD_MESSAGE"
        ws.send_bytes(b"\x00\x01")
        assert ws.receive_json()["code"] == "BAD_MESSAGE"
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json("start")                       # the opening message, not an object
        assert ws.receive_json()["code"] == "EXPECTED_START"


@pytest.mark.parametrize("lat,lon", [(float("nan"), 79.65), (21.17, float("inf")), (True, False), (91, 79), ("21", "79")])
def test_a_position_that_is_not_one_is_not_used(client, lat, lon):
    """JSON as Python reads it allows NaN and Infinity, and True is an int. A
    latitude of NaN went on to be rounded, stored and sent to a weather service."""
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_text(__import__("json").dumps({"type": "start", "lang": "en", "lat": lat, "lon": lon}))
        loc = ws.receive_json()["context"]["location"]
        assert loc["source"] == "farm" and (loc["lat"], loc["lon"]) == (21.17, 79.65)


def test_a_save_that_fails_does_not_cost_the_walk(client, monkeypatch):
    """The database blinks at the one moment that matters. The walk is still in
    memory and nothing was written: the call says so and stays up, and asking
    again saves it."""
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        ws.receive_json()
        read_video(ws, range(860, 866))
        ws.send_json({"type": "end_of_video"})
        ws.receive_json()
        real = live.finish
        monkeypatch.setattr(live, "finish", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("connection reset")))
        ws.send_json({"type": "finish"})
        assert ws.receive_json() == {"type": "error", "code": "SAVE_FAILED"}
        with SessionLocal() as db:
            assert db.query(LiveScan).count() == 0
        monkeypatch.setattr(live, "finish", real)
        ws.send_json({"type": "finish"})
        assert summary_of(ws)["verdict"] == "found"
    with SessionLocal() as db:
        assert db.query(LiveScan).count() == 1


def test_a_frame_the_model_chokes_on_parks_the_walk_instead_of_losing_it(client, monkeypatch):
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = ws.receive_json()["resume"]
        read_video(ws, range(880, 883))
        monkeypatch.setattr(live, "classify", lambda img: 1 / 0)
        ws.send_json(frame_msg(5, 890))
        with pytest.raises(Exception):  # noqa: B017, PT011  the server lets the socket go
            ws.receive_json()
    monkeypatch.setattr(live, "classify", lambda img: [("rice_brown_spot", 0.88)])
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        back = ws.receive_json()
        assert back["resumed"] and back["guide"]["kept"] == 3


def test_an_answer_lost_on_the_way_back_is_given_again_not_saved_twice(client):
    """The line drops in the second between the save and the summary arriving.
    The farmer was told the walk was lost while its result sat in their history.
    Dialling back in with the same token gets the same answer — and no second
    record of the same walk."""
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = ws.receive_json()["resume"]
        read_video(ws, range(900, 906))
        ws.send_json({"type": "end_of_video"})
        ws.receive_json()
        ws.send_json({"type": "finish"})
        first = summary_of(ws)
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        again = ws.receive_json()
        assert again["type"] == "summary" and again["summary"]["scan_id"] == first["scan_id"]
    with SessionLocal() as db:
        assert db.query(LiveScan).count() == 1
    with client.websocket_connect("/api/live/1") as ws:      # and the token is spent
        ws.send_json({"type": "resume", "token": token})
        assert ws.receive_json()["code"] == "RESUME_UNKNOWN"


def test_a_failure_after_the_save_does_not_save_the_walk_twice(client, monkeypatch):
    """The record is written, and then putting the answer together fails. The
    phone is told to ask again — and asking again must find the walk already
    saved, not open the same problem and the same expert case a second time."""
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        ws.receive_json()
        read_video(ws, range(920, 926))
        ws.send_json({"type": "end_of_video"})
        ws.receive_json()
        real = live.speech
        monkeypatch.setattr(live, "speech", lambda *a, **k: 1 / 0)
        ws.send_json({"type": "finish"})
        assert ws.receive_json()["code"] == "SAVE_FAILED"
        monkeypatch.setattr(live, "speech", real)
        ws.send_json({"type": "finish"})
        s = summary_of(ws)
    assert s["verdict"] == "found" and s["seen"][0]["advisory"]["ladder"]
    with SessionLocal() as db:
        assert db.query(LiveScan).count() == 1
        assert db.query(Problem).count() == 1


def test_a_reconnection_that_drops_again_at_once_keeps_the_walk(client):
    """Picking a walk back up hands the phone a new token. On the patchy line
    that made it drop in the first place, it can drop again before that token
    arrives — and the walk was then held under a token the phone never saw, so
    its next try, with the one it did have, was told the walk was gone."""
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        old = ws.receive_json()["resume"]
        read_video(ws, range(940, 944))
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": old})
        # "ready" is sent, and the line is gone before the phone says anything
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": old})
        back = ws.receive_json()
        assert back["resumed"] and back["guide"]["read"] == 4
        newer = back["resume"]
        ws.send_json({"type": "ping"})                      # this time it is heard
        assert ws.receive_json()["type"] == "pong"
    with client.websocket_connect("/api/live/1") as ws:   # the old token is spent now
        ws.send_json({"type": "resume", "token": old})
        assert ws.receive_json()["code"] == "RESUME_UNKNOWN"
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": newer})
        assert ws.receive_json()["guide"]["read"] == 4


# --- after review: the failures between the cracks ---------------------------

def test_a_phone_whose_old_line_is_still_open_can_take_its_call_back(client):
    """Wifi to mobile data leaves the old connection half-open: nothing on it
    says it has gone, and the server only notices after a minute and a half of
    silence. The reconnection comes in long before that and used to be told the
    walk did not exist — it was still attached to the dead line."""
    with client.websocket_connect("/api/live/1") as old:
        old.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = old.receive_json()["resume"]
        read_video(old, range(960, 964))
        # ...and the phone is now on another network, the old line still open
        with client.websocket_connect("/api/live/1") as new:
            new.send_json({"type": "resume", "token": token})
            back = new.receive_json()
            assert back["type"] == "ready" and back["resumed"], back
            assert back["guide"]["read"] == 4
            new.send_json(frame_msg(9, 970, at=9.0))
            assert new.receive_json()["guide"]["kept"] == 5


def test_a_check_that_saw_another_crop_still_says_so_after_the_crop_is_changed(client):
    """The sentence tells the farmer to change the crop for this field if it is
    wrong. When they do, the saved check must not turn into "looks like maize,
    but this field is registered as maize"."""
    import app.routers.live  # noqa: F401  (the route under test)
    from app import live as live_mod

    maize = lambda img: [("maize_healthy", 0.93), ("maize_rust", 0.04)]  # noqa: E731
    live_mod_classify = live_mod.classify
    try:
        live_mod.classify = maize
        with client.websocket_connect("/api/live/1") as ws:
            ws.send_json({"type": "start", "lang": "en", "mode": "video"})
            ws.receive_json()
            read_video(ws, range(980, 986))
            ws.send_json({"type": "end_of_video"})
            ws.receive_json()
            ws.send_json({"type": "finish"})
            s = summary_of(ws)
    finally:
        live_mod.classify = live_mod_classify
    assert s["reading"]["other_crop"]["crop"] == "maize"
    assert "registered as Rice" in s["reading"]["other_crop"]["text"], s["reading"]["other_crop"]["text"]
    with SessionLocal() as db:
        db.get(Farm, 1).crop = "maize"     # the farmer took the advice
        db.commit()
    again = client.get(f"/api/farms/1/live/{s['scan_id']}?lang=en").json()
    assert again["reading"]["other_crop"]["text"] == s["reading"]["other_crop"]["text"]
    hi = client.get(f"/api/farms/1/live/{s['scan_id']}?lang=hi").json()
    assert "धान" in hi["reading"]["other_crop"]["text"], "not re-said in the farmer's language"


def test_a_neighbours_crop_in_the_footage_does_not_overrule_a_finding_on_this_one():
    """Six frames of the maize plot next door, four of a rice disease: that is
    a rice finding, and telling the farmer to pick another field over it is a
    contradiction on one screen."""
    readings = iter([[("maize_healthy", 0.9)]] * 6 + [[("rice_brown_spot", 0.9)]] * 4)
    s = LiveSession(crop="rice", lang="en", can_classify=True, mode="video")
    for seed in range(1000, 1010):
        s.on_frame(leaf(seed), f"n{seed}".encode(), lambda img: next(readings))
    s.ended = True
    assert [x["target"] for x in s.findings(kb)["seen"]] == ["rice_brown_spot"]
    assert s.other_crop_seen() is None and s.why_thin() is None

    healthy = iter([[("maize_healthy", 0.9)]] * 6 + [[("rice_healthy", 0.95)]] * 3)
    s = LiveSession(crop="rice", lang="en", can_classify=True, mode="video")
    for seed in range(1020, 1029):
        s.on_frame(leaf(seed), f"h{seed}".encode(), lambda img: next(healthy))
    assert s.other_crop_seen() is None, "sure looks at healthy rice are an answer about this field"


def test_a_frame_the_model_fails_on_is_undone_whole_and_read_again():
    """Counted half-way, the failed frame left the view looking already seen,
    and the same frame re-sent after the call was picked back up was passed
    over as "the same view": that second of video was never read."""
    for mode in ("video", "walk"):
        s = LiveSession(crop="rice", lang="en", can_classify=True, mode=mode)
        if mode == "walk":
            s.idx = 2                                    # the leaf close-ups
        ok = lambda img: [("rice_brown_spot", 0.9)]      # noqa: E731
        s.on_frame(leaf(1040), b"a", ok, at=0.0)
        before = (s.frames, s.good_frames, s.classified, s.clear, s.kept, s.idx,
                  [st.got for st in s.steps], len(s.closeups), len(s.marks), len(s.sightings))
        with pytest.raises(ZeroDivisionError):
            s.on_frame(leaf(1041), b"b", lambda img: 1 / 0, at=1.0)
        after = (s.frames, s.good_frames, s.classified, s.clear, s.kept, s.idx,
                 [st.got for st in s.steps], len(s.closeups), len(s.marks), len(s.sightings))
        assert after == before, mode
        again = s.on_frame(leaf(1041), b"b", ok, at=1.0)
        assert again["counted"], f"{mode}: the re-sent frame was passed over: {again['quality']}"


def test_a_walk_past_its_time_can_still_be_finished_and_is_not_held_for_ever(client, monkeypatch):
    """A long walk, then a long look-alike question: the farmer's finish arrived
    after the outside edge, was dropped there, and the walk was held, handed
    back and refused again until the phone gave up."""
    import app.routers.live as router

    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        ws.receive_json()
        read_video(ws, range(1060, 1064))
        monkeypatch.setattr(router, "HARD_SECONDS", -1)      # the edge is now behind us
        ws.send_json({"type": "finish"})
        assert summary_of(ws)["reading"]["read"] == 4         # the last word still counts

    monkeypatch.setattr(router, "HARD_SECONDS", 600)
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        token = ws.receive_json()["resume"]
        read_video(ws, range(1070, 1074))
        monkeypatch.setattr(router, "HARD_SECONDS", -1)       # just past the edge
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["code"] == "SESSION_LIMIT"   # told once
        monkeypatch.setattr(router, "HARD_SECONDS", -10_000)  # and now long, long past it
        ws.send_json({"type": "ping"})                         # let go
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "resume", "token": token})
        assert ws.receive_json()["code"] == "RESUME_UNKNOWN", "a call that can only time out was held"


def test_held_calls_are_capped_per_caller_and_answers_do_not_take_their_place():
    import app.routers.live as router

    router._parked.clear()
    router._answered.clear()
    now = time.monotonic()
    walk = lambda who, at: router._Parked(now + at, 1, who, object(), {}, "en", 0.0)  # noqa: E731
    router._hold(("farmer-walk",), walk(7, 0))
    for i in range(router.MAX_ANSWERED + 5):                 # a busy afternoon of finished calls
        router._hold((f"answer-{i}",), router._Parked(now + 1 + i, 1, 8, None, {}, "en", 0.0, {"x": i}))
    for i in range(5):                                       # one account, dropping over and over
        router._hold((f"spam-{i}",), walk(9, 2 + i))
    assert "farmer-walk" in router._parked, "a real dropped walk was pushed out"
    assert sum(1 for t in router._parked if t.startswith("spam-")) == router.MAX_PARKED_PER_CALLER
    assert len(router._answered) == router.MAX_ANSWERED
    # one call under two names is one place, and is picked up once
    router._hold(("new-name", "old-name"), walk(7, 10))
    assert router._unpark("old-name", 1, 7) is not None
    assert "new-name" not in router._parked and router._unpark("new-name", 1, 7) is None


def test_a_save_that_fails_takes_the_photos_it_wrote_with_it(client, monkeypatch):
    from app.config import UPLOAD_DIR

    def files():
        return set(UPLOAD_DIR.glob("*.jpg")) if UPLOAD_DIR.exists() else set()

    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        ws.receive_json()
        read_video(ws, range(1080, 1086))
        ws.send_json({"type": "end_of_video"})
        ws.receive_json()
        before = files()
        real = services._advise
        monkeypatch.setattr(services, "_advise", lambda *a, **k: 1 / 0)   # after the photos are written
        ws.send_json({"type": "finish"})
        assert ws.receive_json()["code"] == "SAVE_FAILED"
        assert files() == before, "the failed attempt left its photos behind"
        monkeypatch.setattr(services, "_advise", real)
        ws.send_json({"type": "finish"})
        s = summary_of(ws)
    assert len(files() - before) == len(s["seen"][0]["evidence"])


@pytest.mark.parametrize("v", [10 ** 400, -(10 ** 400), float("nan"), True, "1", None, 91])
def test_a_number_that_is_not_one_is_refused_at_the_door(v):
    from app.routers.live import _number

    assert _number(v, -90, 90) is None


def test_the_second_that_was_in_flight_when_the_line_dropped_is_read_once():
    s = LiveSession(crop="rice", lang="en", can_classify=True, mode="video")
    ok = lambda img: [("rice_brown_spot", 0.9)]  # noqa: E731
    s.on_frame(leaf(1100), b"a", ok, at=31.0)
    s.on_frame(leaf(1101), b"b", ok, at=32.0)
    again = s.on_frame(leaf(1101), b"b", ok, at=32.0)   # re-sent after the reconnection
    assert again["repeat"] and not again["counted"] and again["mark"] is None
    assert (s.frames, s.kept, len(s.marks)) == (2, 2, 2)
    blur_retry = s.on_frame(leaf(1102), b"c", ok, at=32.5)  # a second look is not a repeat
    assert blur_retry["counted"] and s.frames == 3


def test_past_the_edge_only_a_real_last_word_is_taken(client, monkeypatch):
    """Past the time limit the finish, and an answer to a question actually
    waiting, are still taken. Anything else — an answer to nothing, or the
    same answer over and over — is not a way to keep the place in the queue."""
    import app.routers.live as router

    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        ws.receive_json()
        read_video(ws, range(1120, 1124))
        monkeypatch.setattr(router, "HARD_SECONDS", -1)
        ws.send_json({"type": "answer", "cue_id": "nothing", "answer": "yes"})   # no question was asked
        assert ws.receive_json()["code"] == "SESSION_LIMIT"
        ws.send_json({"type": "answer", "cue_id": "nothing", "answer": "yes"})
        with pytest.raises(Exception):  # noqa: B017, PT011  let go
            ws.receive_json()

    monkeypatch.setattr(router, "HARD_SECONDS", 600)
    with client.websocket_connect("/api/live/1") as ws:
        ws.send_json({"type": "start", "lang": "en", "mode": "video"})
        ws.receive_json()
        read_video(ws, range(1130, 1134))
        monkeypatch.setattr(router, "HARD_SECONDS", -1 - router.LAST_WORD_SECONDS - 5)
        ws.send_json({"type": "finish"})                   # even the finish, once the grace is spent
        with pytest.raises(Exception):  # noqa: B017, PT011
            ws.receive_json()
