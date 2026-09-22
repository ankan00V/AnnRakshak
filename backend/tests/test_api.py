"""The farmer → Doubt Doctor → expert → spread loop over HTTP, with the
network stubbed so tests never depend on a weather API being up."""

import io
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app import geo, services
from app.db import Base, SessionLocal, engine
from app.engine.weather import Day, Window
from app.main import app
from app.models import Alert, Farm


def _leaf_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (320, 240), (60, 140, 50)).save(buf, "JPEG")
    return buf.getvalue()


def _grey_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (320, 240), (128, 128, 128)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture()
def client(monkeypatch):
    humid = Window([Day(date.today() - timedelta(6 - i), 92, 23, 30, 6.0) for i in range(7)], "test", None)
    monkeypatch.setattr(services, "fetch_window", lambda lat, lon: humid)
    monkeypatch.setattr(services, "fetch_month_rain", lambda lat, lon: None)
    # Place lookups stay offline: every district is at Bhandara's headquarters,
    # and any point reverse-geocodes to Kapurthala, Punjab.
    monkeypatch.setattr(geo, "locate", lambda state, district, village=None: {"lat": 21.168, "lon": 79.649})
    monkeypatch.setattr(geo, "reverse", lambda lat, lon: {"state": "Punjab", "district": "Kapurthala", "village": "Phagwara"})
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:
        with SessionLocal() as db:
            sown = date.today() - timedelta(days=60)
            for lat, lon in [(21.17, 79.65), (21.18, 79.66), (21.60, 79.90)]:  # two near, one far
                db.add(Farm(farmer_name="t", crop="rice", sowing_date=sown, district="Bhandara",
                            lat=lat, lon=lon, area_acres=2))
            db.add(Farm(farmer_name="t", crop="cotton", sowing_date=sown, district="Yavatmal",
                        lat=20.39, lon=78.12, area_acres=2))
            db.commit()
        yield c


def diagnose(c, farm_id, scenario, img=None):
    return c.post(f"/api/farms/{farm_id}/diagnose",
                  files={"image": ("x.jpg", img or _leaf_jpeg(), "image/jpeg")},
                  data={"lang": "en", "demo_scenario": scenario}).json()


def test_stub_is_always_labelled(client):
    r = diagnose(client, 1, "clear")
    assert r["is_stub"] is True and r["model_version"] == "stub-0"


def test_no_advisory_outside_advise(client):
    for scenario in ("torn", "unsure"):
        r = diagnose(client, 1, scenario)
        assert r["gate"]["outcome"] != "advise"
        assert "advisory" not in r


def test_clarify_cant_tell_escalates_and_lands_in_bundle(client):
    r = diagnose(client, 1, "torn")
    assert r["gate"]["outcome"] == "clarify"
    out = client.post(f"/api/problems/{r['problem_id']}/clarify",
                      json={"cue_id": r["clarify"]["cue_id"], "answer": "unknown"}).json()
    assert out["outcome"] == "escalate" and "advisory" not in out
    bundle = client.get(f"/api/cases/{out['case']['id']}").json()
    assert bundle["doubt_doctor"][0]["answer"] == "unknown"
    assert bundle["photos"] and bundle["model"]["hypotheses"]


def test_clarify_yes_resolves_to_advice(client):
    r = diagnose(client, 1, "torn")
    out = client.post(f"/api/problems/{r['problem_id']}/clarify",
                      json={"cue_id": r["clarify"]["cue_id"], "answer": "yes"}).json()
    assert out["outcome"] == "advise" and out["advisory"]["ladder"][-1]["tier"] == "chemical"
    assert out["followup"]["id"]


def test_expert_confirmation_spreads_only_within_radius(client):
    r = diagnose(client, 1, "unsure")
    case_id = r["case"]["id"]
    out = client.post(f"/api/cases/{case_id}/resolve", json={
        "verdict": "confirmed", "final_label": "rice_sheath_blight", "expert_name": "KVK"}).json()
    assert out["spread_alerts"] == 1  # farm 2 is ~1.5 km away, farm 3 is ~50 km away
    with SessionLocal() as db:
        spread = db.scalars(select(Alert).where(Alert.trigger == "spread")).all()
        assert [a.farm_id for a in spread] == [2]
    again = client.post(f"/api/cases/{case_id}/resolve", json={
        "verdict": "confirmed", "final_label": "rice_sheath_blight", "expert_name": "KVK"})
    assert again.status_code == 409


def test_unconfirmed_advice_does_not_spread(client):
    diagnose(client, 1, "clear")
    with SessionLocal() as db:
        assert not db.scalars(select(Alert).where(Alert.trigger == "spread")).all()


def test_correction_feeds_prior_and_accuracy(client):
    r = diagnose(client, 1, "unsure")
    client.post(f"/api/cases/{r['case']['id']}/resolve", json={
        "verdict": "corrected", "final_label": "rice_false_smut", "expert_name": "KVK"})
    s = client.get("/api/officials/summary").json()
    assert s["totals"]["corrected"] == 1 and s["totals"]["field_accuracy"] == 0.0
    assert s["accuracy_by_label"][0]["model_label"] == "rice_sheath_blight"


def test_non_crop_photo_asks_retake_without_case(client):
    r = diagnose(client, 1, "clear", img=_grey_jpeg())
    assert r["gate"]["outcome"] == "retake" and "case" not in r


def test_crop_without_photo_model_goes_to_expert(client, monkeypatch):
    """A crop the app cannot check from a photo goes straight to an expert —
    whichever crops ship with a model on the day."""
    from app.kb import get_kb

    monkeypatch.setitem(get_kb().crops["cotton"], "photo_diagnosis", False)
    r = diagnose(client, 4, "clear")
    assert r["gate"]["reason"] == "CROP_NOT_SUPPORTED" and r["case"]["id"]


def test_risk_run_is_idempotent_and_every_alert_has_tasks(client):
    first = client.post("/api/farms/1/risk/run").json()
    second = client.post("/api/farms/1/risk/run").json()
    assert first["issued"] and not second["issued"]
    for a in client.get("/api/farms/1/alerts?lang=mr").json():
        assert len(a["tasks"]) >= 2 and a["reason"]


def test_alert_without_tasks_is_refused_by_the_database(client):
    with SessionLocal() as db:
        db.add(Alert(farm_id=1, target="rice_brown_spot", trigger="weather", level="low",
                     reason={"en": "x"}, tasks={"en": []}, issued_on=date.today()))
        with pytest.raises(Exception):
            db.commit()


def test_followup_got_worse_escalates(client):
    r = diagnose(client, 1, "clear")
    out = client.post(f"/api/followups/{r['followup']['id']}", json={"response": "got_worse"}).json()
    assert out["case"]["reason"] == "FOLLOWUP_WORSE"


def test_healthy_label_gets_a_localized_name():
    from app.engine.gate import Prediction
    from app.kb import get_kb

    kb = get_kb()
    assert services._pred_view(kb, Prediction("maize_healthy", 0.04), "en")["name"] == "Healthy Maize"
    assert services._pred_view(kb, Prediction("rice_healthy", 0.04), "mr")["name"].startswith("निरोगी")


def test_expert_bundle_carries_icar_referral(client):
    r = diagnose(client, 1, "clear")  # stub: rice bacterial leaf blight above the gate
    esc = client.post(f"/api/problems/{r['problem_id']}/escalate").json()
    bundle = client.get(f"/api/cases/{esc['case']['id']}").json()
    ids = [x["id"] for x in bundle["icar_referral"]]
    assert "nrri_clcc" in ids and "nrri_ricexpert" in ids  # target-linked first, then crop-level
    assert ids.index("nrri_clcc") < ids.index("nrri_ricexpert")


def test_outlook_lists_icar_inputs_to_stock(client):
    client.post("/api/officials/risk/run-all")
    rows = client.get("/api/officials/outlook").json()
    assert rows
    for row in rows:
        assert all(x["type"] in ("biocontrol", "variety", "monitoring") for x in row["icar_inputs"])
    assert any(row["icar_inputs"] for row in rows)


def test_sarvam_key_pool_benches_an_exhausted_key_and_fails_over():
    from app.voice import KeyPool, VoiceUnavailable

    class Err(Exception):
        def __init__(self, code):
            self.status_code = code

    pool = KeyPool(["k1", "k2", "k3"])
    pool._client = lambda i: i  # the "client" is just the key index
    used = []

    def call(i):
        used.append(i)
        if i == 0:
            raise Err(402)  # out of credits
        return f"ok{i}"

    assert pool.call(call) == "ok1" and used == [0, 1]
    assert pool.status() == {"keys": 3, "benched": 1}
    used.clear()
    for _ in range(3):
        pool.call(call)
    assert 0 not in used  # benched key is skipped while others work

    with pytest.raises(ValueError):  # a bad request is not the key's fault: raised, nothing benched
        pool.call(lambda i: (_ for _ in ()).throw(ValueError("bad input")))
    assert pool.status()["benched"] == 1

    rate = KeyPool(["a"])
    rate._client = lambda i: i
    with pytest.raises(VoiceUnavailable):
        rate.call(lambda i: (_ for _ in ()).throw(Err(429)))


def test_rate_limit_counts_per_window_without_redis():
    from fastapi import HTTPException

    from app import cache
    from app.limits import limit

    for _ in range(3):
        limit("unit-test-key", 3, 60)
    with pytest.raises(HTTPException) as e:
        limit("unit-test-key", 3, 60)
    assert e.value.status_code == 429 and e.value.headers["Retry-After"] == "60"
    assert cache.leader("watch", 60)  # no Redis: this process is its own leader
    assert not cache.publish(1, {"type": "notice"})  # no Redis: caller delivers locally


def test_result_reopens_in_another_language(client):
    """Switching language on the result screen re-renders it from what was stored."""
    r = client.post("/api/farms/1/diagnose", files={"image": ("x.jpg", _leaf_jpeg(), "image/jpeg")},
                    data={"lang": "hi", "demo_scenario": "clear"}).json()
    assert r["gate"]["outcome"] == "advise"
    en = client.get(f"/api/problems/{r['problem_id']}/result?lang=en").json()
    assert en["gate"] | {"alternatives": None} == r["gate"] | {"alternatives": None}
    assert [a["id"] for a in en["gate"]["alternatives"]] == [a["id"] for a in r["gate"]["alternatives"]]
    assert en["advisory"]["target"] == r["advisory"]["target"] and en["advisory"]["name"] != r["advisory"]["name"]
    assert en["advisory"]["name"].isascii() and en["followup"] == r["followup"]


def test_result_reopens_as_things_stand_now(client):
    r = diagnose(client, 1, "torn")
    first = client.get(f"/api/problems/{r['problem_id']}/result?lang=mr").json()
    assert first["gate"]["outcome"] == "clarify" and first["clarify"]["cue_id"] == r["clarify"]["cue_id"]
    client.post(f"/api/problems/{r['problem_id']}/clarify", json={"cue_id": r["clarify"]["cue_id"], "answer": "yes"})
    after = client.get(f"/api/problems/{r['problem_id']}/result?lang=mr").json()
    assert after["gate"]["outcome"] == "advise" and after["advisory"]["ladder"]
    client.post(f"/api/problems/{r['problem_id']}/escalate?lang=mr")
    asked = client.get(f"/api/problems/{r['problem_id']}/result?lang=en").json()
    assert asked["gate"]["outcome"] == "escalate" and asked["case"]["id"]


def test_field_location_is_recorded_and_used(client):
    """Weather, the spray window and the 5 km outbreak radius are all read at
    the field's spot, so the app tracks whether it has a real one."""
    before = client.get("/api/farms/1?lang=en").json()
    assert before["location_source"] == "district"  # seeded from the district headquarters
    after = client.patch("/api/farms/1", json={"lat": 21.1809, "lon": 79.6612}).json()
    assert after["location_source"] == "gps" and (after["lat"], after["lon"]) == (21.1809, 79.6612)
    with SessionLocal() as db:
        farm = db.get(Farm, 1)
        assert farm.agro_polygon_id is None  # the satellite field polygon is redrawn there
    assert client.patch("/api/farms/1", json={"lang": "mr"}).json()["location_source"] == "gps"


def test_a_far_away_phone_fix_needs_the_farmer_to_confirm_it(client):
    """A laptop in Punjab once moved Bhandara farms 1,100 km: a fix far from the
    district is refused until the farmer confirms, and then the district follows."""
    r = client.patch("/api/farms/1", json={"lat": 31.25, "lon": 75.70})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "far_from_district"
    assert r.json()["detail"]["km"] > 1000
    assert client.get("/api/farms/1?lang=en").json()["lat"] == 21.17  # unchanged
    ok = client.patch("/api/farms/1", json={"lat": 31.25, "lon": 75.70, "confirm_far": True}).json()
    assert (ok["lat"], ok["district"], ok["location_source"]) == (31.25, "Kapurthala", "gps")


def test_a_demo_farm_never_moves_to_the_viewers_location(client):
    with SessionLocal() as db:
        db.get(Farm, 2).is_demo = True
        db.commit()
    r = client.patch("/api/farms/2", json={"lat": 21.181, "lon": 79.661})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "demo_farm"


# --------------------------------------------------------------------------
# Voice providers: Bhashini first, Sarvam behind it
# --------------------------------------------------------------------------

def _float_wav(seconds=0.1, rate=16000):
    import io, struct
    import numpy as np
    x = (np.sin(np.linspace(0, 50, int(seconds * rate))) * 0.5).astype("<f4").tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(x)) + x
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_bhashini_float_speech_becomes_pcm_every_browser_plays():
    import io, wave
    from app import bhashini
    with wave.open(io.BytesIO(bhashini.pcm16(_float_wav()))) as w:  # the wave module rejects float WAV
        assert (w.getsampwidth(), w.getframerate(), w.getnchannels()) == (2, 16000, 1)


def test_voice_falls_back_to_sarvam_when_bhashini_fails(monkeypatch):
    from app import bhashini, voice
    monkeypatch.setattr(bhashini, "enabled", lambda: True)
    monkeypatch.setattr(voice.pool, "keys", ["k"])
    def broken(*a, **k):
        raise bhashini.BhashiniError("down")
    monkeypatch.setattr(bhashini, "translate", broken)
    monkeypatch.setattr(voice, "_sarvam_translate", lambda t, s, g: "सरवम")
    assert voice.translate("hello", "en", "hi") == "सरवम"


def test_voice_prefers_bhashini_and_never_calls_sarvam_when_it_works(monkeypatch):
    from app import bhashini, voice
    monkeypatch.setattr(bhashini, "enabled", lambda: True)
    monkeypatch.setattr(voice.pool, "keys", ["k"])
    monkeypatch.setattr(bhashini, "translate", lambda t, s, g: "भाषिणी")
    def must_not_run(*a, **k):
        raise AssertionError("Sarvam was called although Bhashini answered")
    monkeypatch.setattr(voice, "_sarvam_translate", must_not_run)
    assert voice.translate("hello", "en", "hi") == "भाषिणी"


def test_no_voice_provider_is_a_clear_503(monkeypatch):
    from app import bhashini, voice
    monkeypatch.setattr(bhashini, "enabled", lambda: False)
    monkeypatch.setattr(voice.pool, "keys", [])
    with pytest.raises(voice.VoiceUnavailable):
        voice.translate("hello", "en", "hi")


def test_a_language_bhashini_just_failed_on_is_skipped_for_a_while(monkeypatch):
    import httpx
    from app import bhashini
    monkeypatch.setattr(bhashini, "BHASHINI_INFERENCE_KEY", "test-key")
    calls = []
    def slow(*a, **k):
        calls.append(1)
        raise httpx.ReadTimeout("hung")
    monkeypatch.setattr(bhashini.httpx, "post", slow)
    for _ in range(3):
        with pytest.raises(bhashini.BhashiniError):
            bhashini.tts("ନମସ୍କାର", "gu")
    assert len(calls) == 1  # one farmer waited; the next two were not made to


def test_bhashini_is_asked_for_odia_by_its_iso_code(monkeypatch):
    from app import bhashini
    assert bhashini._code("od") == "or" and bhashini._code("hi") == "hi"


def test_the_spray_verdict_never_waits_on_the_ai_note(client, monkeypatch):
    """The verified answer comes back without touching the model; the AI note is
    a separate call. A slow model once dropped notes at random by timing out
    inside the verdict request."""
    from app import llm
    monkeypatch.setattr(llm, "enabled", lambda: True)
    def must_not_run(*a, **k):
        raise AssertionError("the verdict called the model")
    monkeypatch.setattr(llm, "suggest", must_not_run)
    v = client.post("/api/labelcheck", json={"farm_id": 1, "product": "water", "lang": "en"}).json()
    assert v["tone"] == "unknown" and v["note_available"] is True and "suggestion" not in v


def test_the_ai_note_is_only_for_what_we_have_no_record_of(client, monkeypatch):
    from app import llm
    monkeypatch.setattr(llm, "suggest", lambda *a, **k: "Water is just water. It does not treat this.")
    known = client.post("/api/labelcheck/note", json={"farm_id": 1, "product": "mancozeb", "lang": "en"}).json()
    assert known["suggestion"] is None  # a registered product gets the verified answer only
    unknown = client.post("/api/labelcheck/note", json={"farm_id": 1, "product": "water", "lang": "en"}).json()
    assert unknown["suggestion"].startswith("Water is just water")


def test_the_ai_note_is_written_in_english_then_translated(client, monkeypatch):
    """The model writes English (fast, and what the safety guard reads); the
    farmer's language comes from the translator. A failed translation shows the
    English rather than no note."""
    from app import cache, llm, voice
    asked: list[str] = []
    monkeypatch.setattr(llm, "suggest", lambda product, crop, problem, lang, **k: asked.append(lang) or "Salt is not a pesticide.")
    monkeypatch.setattr(voice, "translate", lambda text, s, t: f"[{t}] {text}")
    monkeypatch.setattr(cache, "get_json", lambda key: None)
    monkeypatch.setattr(cache, "set_json", lambda *a, **k: None)
    hi = client.post("/api/labelcheck/note", json={"farm_id": 1, "product": "salt", "lang": "hi"}).json()
    assert hi["suggestion"] == "[hi] Salt is not a pesticide." and asked == ["en"]

    def down(*a):
        raise RuntimeError("translator down")
    monkeypatch.setattr(voice, "translate", down)
    ta = client.post("/api/labelcheck/note", json={"farm_id": 1, "product": "salt", "lang": "ta"}).json()
    assert ta["suggestion"] == "Salt is not a pesticide."
