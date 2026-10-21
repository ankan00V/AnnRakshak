"""The farmer → Doubt Doctor → expert → spread loop over HTTP, with the
network stubbed so tests never depend on a weather API being up."""

import io
from collections import Counter
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app import cache, geo, services
from app.db import Base, SessionLocal, engine
from app.engine import phenology
from app.engine.weather import Day, Window
from app.main import app
from app.models import Alert, Case, Farm, OfficerAction, Problem, Season


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
    cache._counts.clear()  # rate-limit windows are process-wide; don't bill the next test
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


def _officers(n=5, district="Bhandara", verified=True):
    """n verified officers covering one district."""
    from app.models import ExpertProfile, User
    ids = []
    with SessionLocal() as db:
        for i in range(n):
            u = User(role="expert", name=f"Officer {i + 1}", email=f"officer{i + 1}@kvk.test")
            db.add(u)
            db.flush()
            db.add(ExpertProfile(user_id=u.id, designation="kvk_scientist", organisation="KVK",
                                 employee_id=f"E{i}", qualification="msc_agri", experience_years=5,
                                 districts=[district], crops=["rice"], specialities=["plant_pathology"],
                                 languages=["en"], verified=verified))
            ids.append(u.id)
        db.commit()
    return ids


def test_cases_spread_across_the_districts_officers(client):
    """Five officers, five escalations: nobody is handed a second while another
    is still empty."""
    ids = _officers(5)
    for _ in range(5):
        r = diagnose(client, 1, "unsure")
        assert r["gate"]["outcome"] == "escalate"
    with SessionLocal() as db:
        from app.models import Case
        holding = Counter(c.assigned_to for c in db.scalars(select(Case)).all())
    assert set(holding) == set(ids) and set(holding.values()) == {1}


def test_next_case_goes_to_the_officer_holding_least(client):
    ids = _officers(5)
    first = diagnose(client, 1, "unsure")  # a real problem to hang the load on
    with SessionLocal() as db:
        from app.models import Case
        problem_id = db.get(Case, first["case"]["id"]).problem_id
        # 4, 6, 8, 2, 5 open cases, as if the morning had already happened.
        for uid, load in zip(ids, [4, 6, 8, 2, 5], strict=True):
            held = db.scalar(select(func.count(Case.id)).where(
                Case.assigned_to == uid, Case.status == "open")) or 0
            for _ in range(load - held):
                db.add(Case(problem_id=problem_id, reason="BELOW_FLOOR", status="open",
                            assigned_to=uid, assigned_at=datetime.now()))
        db.commit()
    r = diagnose(client, 1, "unsure")
    with SessionLocal() as db:
        from app.models import Case
        case = db.get(Case, r["case"]["id"])
        assert case.assigned_to == ids[3]  # the one holding 2


def test_a_case_in_a_district_with_no_officer_stays_in_everyones_queue(client):
    _officers(2, district="Nagpur")  # nobody covers Bhandara...
    r = diagnose(client, 1, "unsure")
    with SessionLocal() as db:
        from app.models import Case
        # ...so it still gets routed rather than stranded: the fallback is every officer.
        assert db.get(Case, r["case"]["id"]).assigned_to is not None


def test_unverified_officers_are_never_given_cases(client):
    _officers(3, verified=False)
    r = diagnose(client, 1, "unsure")
    with SessionLocal() as db:
        from app.models import Case
        assert db.get(Case, r["case"]["id"]).assigned_to is None


def test_supervisor_can_route_a_backlog_and_see_the_load(client):
    """Cases raised before any officer existed are not stranded: the office
    presses route once and they land on the freest desks."""
    for _ in range(4):
        diagnose(client, 1, "unsure")
    before = client.get("/api/officials/workload").json()
    assert before["unassigned"] == 4 and before["officers"] == []

    ids = _officers(2)
    routed = client.post("/api/officials/cases/route").json()
    assert routed == {"considered": 4, "assigned": 4}

    after = client.get("/api/officials/workload").json()
    assert after["unassigned"] == 0 and after["open_total"] == 4
    assert sorted(o["open_cases"] for o in after["officers"]) == [2, 2]  # split evenly
    assert {o["user_id"] for o in after["officers"]} == set(ids)
    assert all(o["oldest_wait_hours"] is not None for o in after["officers"])


def test_a_case_can_be_placed_by_name_when_there_is_nobody_to_be(client):
    """These flows run with sign-in off, where there is no officer to be and so
    no supervisor to check. Who may place a case by name when sign-in is on is
    held in test_auth.py."""
    ids = _officers(3)
    r = diagnose(client, 1, "unsure")
    case_id = r["case"]["id"]
    out = client.post(f"/api/cases/{case_id}/reassign", json={"to_user_id": ids[2]}).json()
    assert out["assigned_to"] == ids[2]
    assert client.get(f"/api/cases/{case_id}").json()["case"]["assigned_to"] == ids[2]


def test_handing_a_case_on_without_a_name_finds_the_freest_officer(client):
    ids = _officers(2)
    first = diagnose(client, 1, "unsure")["case"]["id"]
    second = diagnose(client, 1, "unsure")["case"]["id"]
    # Both officers now hold one. Handing the first on must not give it back to
    # its current holder while the other is equally free.
    holder = client.get(f"/api/cases/{first}").json()["case"]["assigned_to"]
    out = client.post(f"/api/cases/{first}/reassign", json={}).json()
    assert out["assigned_to"] in ids and out["assigned_to"] != holder
    assert client.get(f"/api/cases/{second}").json()["case"]["assigned_to"] is not None


def test_the_only_officer_in_a_district_keeps_a_case_handed_on(client):
    """Nobody else to give it to: better the same desk than nobody's."""
    ids = _officers(1)
    case_id = diagnose(client, 1, "unsure")["case"]["id"]
    assert client.post(f"/api/cases/{case_id}/reassign", json={}).json()["assigned_to"] == ids[0]


def test_a_resolved_case_cannot_be_handed_on(client):
    _officers(2)
    case_id = diagnose(client, 1, "unsure")["case"]["id"]
    client.post(f"/api/cases/{case_id}/resolve", json={
        "verdict": "confirmed", "final_label": "rice_brown_spot", "expert_name": "Dr. Kale"})
    assert client.post(f"/api/cases/{case_id}/reassign", json={}).status_code == 409


def test_expert_can_record_a_healthy_plant(client):
    """The model saw a disease; the officer looked and the crop is fine."""
    _officers(2)
    case_id = diagnose(client, 1, "unsure")["case"]["id"]
    out = client.post(f"/api/cases/{case_id}/resolve", json={
        "verdict": "confirmed", "final_label": "healthy", "expert_name": "Dr. Kale"}).json()
    assert out["final_label"] == "healthy"
    assert out["verdict"] == "corrected"      # the model put forward a disease and was wrong
    assert out["spread_alerts"] == 0          # nobody is warned about a healthy field
    assert out["followup"] is None            # and there is nothing to follow up


def test_expert_can_record_something_the_app_cannot_name(client):
    _officers(2)
    case_id = diagnose(client, 1, "unsure")["case"]["id"]
    out = client.post(f"/api/cases/{case_id}/resolve", json={
        "verdict": "corrected", "final_label": "other", "expert_name": "Dr. Kale",
        "notes": "Zinc deficiency — interveinal chlorosis on the older leaves."}).json()
    assert out["final_label"] == "other" and out["spread_alerts"] == 0
    # No authored advisory exists for it, so the app offers none.
    assert out["followup"] is None


def test_something_else_must_be_named(client):
    _officers(2)
    case_id = diagnose(client, 1, "unsure")["case"]["id"]
    r = client.post(f"/api/cases/{case_id}/resolve", json={
        "verdict": "corrected", "final_label": "other", "expert_name": "Dr. Kale"})
    assert r.status_code == 422 and "note" in r.json()["detail"]


def test_a_sentinel_verdict_teaches_the_prior_nothing(client):
    """'Healthy' is not a label the model can be nudged towards."""
    from app.models import LabelPrior
    _officers(2)
    case_id = diagnose(client, 1, "unsure")["case"]["id"]
    client.post(f"/api/cases/{case_id}/resolve", json={
        "verdict": "confirmed", "final_label": "healthy", "expert_name": "Dr. Kale"})
    with SessionLocal() as db:
        rows = db.scalars(select(LabelPrior)).all()
        assert all(r.target not in ("healthy", "other") for r in rows)
        assert all(r.confirmed == 0 for r in rows)  # only the model's own guess was marked wrong


def test_the_queue_narrows_the_way_an_officer_narrows_it(client):
    """District, crop, search and 'past the SLA' are how a queue becomes work."""
    _officers(2)
    for _ in range(2):
        diagnose(client, 1, "unsure")          # farm 1: rice, Bhandara
    diagnose(client, 4, "unsure")              # farm 4: cotton, Yavatmal

    def ids(**q):
        return {c["id"] for c in client.get("/api/cases", params={"status": "open", **q}).json()}

    everything = ids()
    assert len(everything) == 3
    assert len(ids(district="Bhandara")) == 2
    assert len(ids(crop="cotton")) == 1
    assert ids(district="Bhandara") | ids(district="Yavatmal") == everything
    assert ids(q_text="Yavatmal") == ids(district="Yavatmal")
    assert ids(overdue=True) == set()          # nothing has been waiting a day yet


def test_a_morning_of_triage_moves_in_one_press(client):
    ids = _officers(3)
    cases = [diagnose(client, 1, "unsure")["case"]["id"] for _ in range(4)]
    with SessionLocal() as db:
        from app.models import Case
        for c in db.scalars(select(Case)).all():      # pile them all on one desk
            c.assigned_to = ids[0]
        db.commit()

    out = client.post("/api/cases/bulk/assign", json={"case_ids": cases, "to_user_id": None}).json()
    assert out == {"moved": 4, "skipped": 0}
    with SessionLocal() as db:
        from app.models import Case
        holders = Counter(db.get(Case, cid).assigned_to for cid in cases)
    assert max(holders.values()) <= 2 and len(holders) >= 2   # spread, not stacked


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


def test_the_summary_counts_one_side_of_the_demo_line(client):
    """The dashboard's headline and the queue below it must agree. The summary
    used to read every farm, so a demo case was counted for a real district."""
    diagnose(client, 1, "unsure")                       # a real farm's case
    with SessionLocal() as db:
        demo = Farm(farmer_name="demo", crop="rice", sowing_date=date.today() - timedelta(days=60),
                    district="Bhandara", lat=21.17, lon=79.65, area_acres=2, is_demo=True)
        db.add(demo)
        db.commit()
        demo_id = demo.id
    diagnose(client, demo_id, "unsure")                 # and a demo farm's case

    s = client.get("/api/officials/summary").json()     # signed out: the real side
    assert s["includes_demo_data"] is False
    assert s["totals"]["farms"] == 4 and s["totals"]["open_cases"] == 1


def test_the_map_and_the_sweep_stay_on_one_side_of_the_demo_line(client):
    """A pin carries a farmer's name and their field's coordinates, and the
    sweep writes alerts. Neither may cross between demo and real."""
    diagnose(client, 1, "unsure")                       # a real farm's problem
    with SessionLocal() as db:
        demo = Farm(farmer_name="Demo Sunita", crop="rice", sowing_date=date.today() - timedelta(days=60),
                    district="Bhandara", lat=21.17, lon=79.65, area_acres=2, is_demo=True)
        db.add(demo)
        db.commit()
        demo_id = demo.id
    diagnose(client, demo_id, "unsure")

    # Signed out is the real side: the demo farmer must not appear on the map,
    # in its pins or in the alert layer that carries the same coordinates.
    spots = client.get("/api/officials/hotspots").json()
    names = [p["farmer_name"] for p in spots["points"]]
    assert names and "Demo Sunita" not in names
    with SessionLocal() as db:
        demo_farm = db.get(Farm, demo_id)
        assert all(a["lat"] != demo_farm.lat or a["lon"] != demo_farm.lon
                   for a in spots["active_alerts"])

    before = _alert_count()
    client.post("/api/officials/risk/run-all")
    assert _alert_count() >= before                     # it may issue for real farms
    with SessionLocal() as db:                          # but never for the demo one
        assert not db.scalars(select(Alert).where(Alert.farm_id == demo_id)).all()


def _alert_count() -> int:
    with SessionLocal() as db:
        return len(db.scalars(select(Alert)).all())


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
    # The farmer says it got worse, and sends what they saw with it: this is
    # the evidence the district office used to receive none of.
    out = client.post(f"/api/followups/{r['followup']['id']}",
                      data={"response": "got_worse", "note": "Spots have spread to the top leaves."},
                      files={"image": ("worse.jpg", _leaf_jpeg(), "image/jpeg")}).json()
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


def _alert(farm_id, target, level, days_ago, trigger="weather"):
    """An alert the database will accept: it insists every alert carries at
    least one English task, and that one farm sees one target per trigger
    per day."""
    return Alert(farm_id=farm_id, target=target, trigger=trigger, level=level,
                 reason={"en": "humid week"}, tasks={"en": ["Walk the field"]},
                 issued_on=date.today() - timedelta(days=days_ago))


def test_the_picker_says_which_field_is_in_trouble(client):
    """A farmer with several fields should not have to open each one to find
    the one the app is worried about."""
    with SessionLocal() as db:
        db.add_all([
            _alert(1, "rice_blast", "medium", 2),
            _alert(1, "rice_bacterial_leaf_blight", "high", 4),
            _alert(2, "rice_blast", "high", 40),   # real once, not "right now"
        ])
        db.commit()

    farms = {f["id"]: f for f in client.get("/api/farms").json()}
    assert farms[1]["alert"]["level"] == "high", "the worst of the week wins, not the most recent"
    assert farms[1]["alert"]["name"], "named in the farmer's language, not as a target id"
    assert farms[2]["alert"] is None, "six weeks old is not what stands against it today"
    assert farms[3]["alert"] is None


def test_the_picker_reads_the_alerts_once_however_many_fields(client):
    """This runs on every landing; it must not walk the farms one at a time."""
    from sqlalchemy import event

    from app.db import engine as eng

    with SessionLocal() as db:
        db.add_all([_alert(i, "rice_blast", "low", 1) for i in (1, 2, 3)])
        db.commit()

    reads = []

    def count(conn, cursor, statement, *a):
        if "FROM alert" in statement:
            reads.append(statement)

    event.listen(eng, "before_cursor_execute", count)
    try:
        client.get("/api/farms")
    finally:
        event.remove(eng, "before_cursor_execute", count)
    assert len(reads) == 1, f"one read for the whole list, got {len(reads)}"


def test_a_case_nobody_answers_moves_to_the_next_desk_on_its_own(client):
    """The district promises a farmer 24 hours; one desk gets eight of them.
    Past that the case moves without anyone having to chase it."""
    from datetime import datetime as dt

    from app.config import CASE_RESPONSE_HOURS, MAX_CASE_HANDOVERS
    from app.kb import get_kb

    ids = _officers(3)
    case_id = diagnose(client, 1, "unsure")["case"]["id"]
    with SessionLocal() as db:
        case = db.get(Case, case_id)
        first = case.assigned_to
        assert first in ids
        assert case.response_due_at is not None, "assignment must start a clock"
        # Nothing is due yet, so nothing moves.
        assert services.sweep_overdue_cases(db, kb=get_kb())["moved"] == 0

        case.response_due_at = dt.now() - timedelta(minutes=1)
        db.commit()
        assert services.sweep_overdue_cases(db, kb=get_kb())["moved"] == 1

    with SessionLocal() as db:
        case = db.get(Case, case_id)
        assert case.assigned_to != first, "it must not go back to the desk that let it lapse"
        assert case.handovers == 1 and first in (case.passed_over or [])
        assert case.response_due_at > dt.now()          # the new desk gets its own clock
        moved = db.scalar(select(OfficerAction).where(OfficerAction.action == "auto_handover"))
        assert moved is not None and moved.detail["from_user_id"] == first


def test_a_case_stops_circulating_once_everyone_has_had_it(client):
    """A case nobody will answer is a staffing problem. Passing it round for
    ever is how that stays invisible, so the passing stops and it waits."""
    from datetime import datetime as dt

    from app.config import MAX_CASE_HANDOVERS
    from app.kb import get_kb

    _officers(2)
    case_id = diagnose(client, 1, "unsure")["case"]["id"]
    for _ in range(MAX_CASE_HANDOVERS + 2):
        with SessionLocal() as db:
            case = db.get(Case, case_id)
            case.response_due_at = dt.now() - timedelta(minutes=1)
            db.commit()
            services.sweep_overdue_cases(db, kb=get_kb())
    with SessionLocal() as db:
        assert db.get(Case, case_id).handovers <= MAX_CASE_HANDOVERS


def kb_for_tests():
    from app.kb import get_kb
    return get_kb()


def test_a_field_outlives_its_crop(client):
    """A farm row is the field, not the sowing. The season closes, the row
    stays, and sowing again is a new season on the same field — which is the
    whole point: a farmer growing rice a second year should not end up with
    two rice farms in their list."""
    before = len(client.get("/api/farms").json())

    r = client.post("/api/farms/1/harvest", json={"note": "cut on time"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "fallow" and r.json()["harvested_on"]

    with SessionLocal() as db:
        farm = db.get(Farm, 1)
        assert farm.status == "fallow"
        assert [s.crop for s in farm.seasons] == ["rice"]

    r = client.post("/api/farms/1/sow", json={"crop": "rice", "sowing_date": date.today().isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "growing" and r.json()["das"] == 0

    assert len(client.get("/api/farms").json()) == before, "the field was not cloned"
    with SessionLocal() as db:
        assert len(db.get(Farm, 1).seasons) == 1, "the finished season is kept as history"


def test_a_fallow_field_is_not_warned_about(client, monkeypatch):
    """The risk engine must leave a field alone once the crop is off it."""
    client.post("/api/farms/2/harvest", json={})
    with SessionLocal() as db:
        out = services.run_risk(db, kb_for_tests(), db.get(Farm, 2))
    assert out["issued"] == [] and out["why"] == "field is fallow"


def test_a_harvested_field_stops_counting_days(client):
    """The complaint this exists for: a field that was cut in November was
    still gaining a day every morning, so by spring the app called it 260 days
    old and read a maturing stage off a bare plot. The clock stops at the
    harvest and stays stopped."""
    on = date.today() - timedelta(days=30)
    r = client.post("/api/farms/1/harvest", json={"harvested_on": on.isoformat()})
    assert r.status_code == 200, r.text
    frozen = r.json()["das"]

    with SessionLocal() as db:
        farm = db.get(Farm, 1)
        later = services.farm_view(kb_for_tests(), farm, "en", today=date.today() + timedelta(days=45))
    assert later["das"] == frozen, "a fallow field kept ageing"
    assert frozen == (on - date.fromisoformat(client.get("/api/farms/1").json()["sowing_date"])).days

    # Sowing again starts the next season's clock from zero.
    client.post("/api/farms/1/sow", json={"crop": "rice", "sowing_date": date.today().isoformat()})
    assert client.get("/api/farms/1").json()["das"] == 0


def test_a_field_nobody_closes_stops_at_the_end_of_its_season(client):
    """The half a button cannot fix. A farmer who never presses anything had a
    field gaining a day every morning for ever: sown in June, and by the next
    summer "380 days old" and still reading a maturity stage off bare ground,
    with the risk engine still scoring blast on it.

    Nothing here is pressed. The clock stops at the crop's own season end, the
    engine stops with it, and the field says it wants closing."""
    with SessionLocal() as db:
        farm = db.get(Farm, 1)
        farm.sowing_date = date.today() - timedelta(days=380)
        farm.date_basis = "sown"
        db.commit()

    f = client.get("/api/farms/1").json()
    end = kb_for_tests().season_ends("rice")
    assert f["das"] == end, f"days ran past the season to {f['das']}"
    assert f["season_over"] is True
    assert f["status"] == "dormant", "nothing was pressed; the field had to settle itself"

    # And the listing persists it, so a district's totals stop counting it.
    client.get("/api/farms")
    with SessionLocal() as db:
        assert db.get(Farm, 1).status == "dormant"

    with SessionLocal() as db:
        out = services.run_risk(db, kb_for_tests(), db.get(Farm, 1))
    assert out["issued"] == [] and out["why"] == "season is over"


def test_a_crop_that_is_still_standing_keeps_its_warnings(client):
    """The danger in stopping a clock automatically. A season end read off a
    crop calendar is a generalisation, and a field that genuinely runs past it
    must not have its disease warnings switched off on the strength of one —
    that would trade a wrong number for a missed outbreak. The farmer says the
    crop is still there, and the field goes back to work."""
    kb = kb_for_tests()
    with SessionLocal() as db:
        farm = db.get(Farm, 1)
        farm.sowing_date = date.today() - timedelta(
            days=kb.season_ends("rice") + phenology.HARVEST_GRACE_DAYS + 5)
        farm.date_basis = "sown"
        db.commit()
    assert client.get("/api/farms/1").json()["season_over"] is True

    f = client.post("/api/farms/1/standing").json()
    assert f["status"] == "growing" and f["season_over"] is False
    with SessionLocal() as db:
        out = services.run_risk(db, kb, db.get(Farm, 1))
    assert out.get("why") != "season is over", "a standing crop was left unscored"

    # Held open, not for ever: it asks again a month later.
    later = date.today() + timedelta(days=services.STILL_STANDING_DAYS + 1)
    with SessionLocal() as db:
        assert services.farm_view(kb, db.get(Farm, 1), "en", today=later)["season_over"] is True


def test_sowing_again_after_a_field_went_quiet_keeps_one_row(client):
    """The clone problem, from the state a farmer actually arrives in: they
    stopped opening the app, the field went dormant on its own, and months
    later they sow it again. Still one row, and the season that lapsed is
    recorded as ending at its season end rather than on the day of the new
    sowing."""
    kb = kb_for_tests()
    before = len(client.get("/api/farms").json())
    with SessionLocal() as db:
        farm = db.get(Farm, 1)
        farm.sowing_date = date.today() - timedelta(days=300)
        farm.date_basis = "sown"
        db.commit()
        # The lapsed season is recorded as ending at the harvest we predicted,
        # not at the grace deadline that followed it.
        end = services.expected_harvest(kb, farm).on
    client.get("/api/farms")  # the listing settles it

    r = client.post("/api/farms/1/sow", json={"crop": "rice", "sowing_date": date.today().isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "growing" and r.json()["das"] == 0
    assert len(client.get("/api/farms").json()) == before, "the field was cloned"
    with SessionLocal() as db:
        seasons = db.get(Farm, 1).seasons
        assert [s.harvested_on for s in seasons] == [end], "the lapsed season got the wrong end date"


def test_an_escalated_alert_reaches_the_officer_with_evidence(client):
    """The report: a farmer says the crop got worse, and the district office
    opens a case with a blank frame and one line of generated text. Nobody can
    act on that. The farmer is the only person who has stood in the field, so
    what they send is the whole of the evidence."""
    r = client.post("/api/farms/1/diagnose", files={"image": ("x.jpg", _leaf_jpeg(), "image/jpeg")},
                    data={"demo_scenario": "clear"}).json()
    fid = r["followup"]["id"]
    out = client.post(f"/api/followups/{fid}",
                      data={"response": "got_worse", "note": "Spots have spread to the top leaves."},
                      files={"image": ("worse.jpg", _leaf_jpeg(), "image/jpeg")}).json()

    with SessionLocal() as db:
        bundle = services.case_bundle(db, kb_for_tests(), db.get(Case, out["case"]["id"]))

    assert len(bundle["photos"]) >= 2, "the photo the farmer sent with the escalation is missing"
    assert any("spread to the top leaves" in o["answer"] for o in bundle["farmer_report"]), \
        "the officer cannot read what the farmer actually said"


def test_an_escalation_without_a_photo_says_so(client):
    """A farmer who cannot photograph it still gets to report it — and the
    case says there is no photograph rather than showing an empty frame."""
    r = client.post("/api/farms/1/diagnose", files={"image": ("x.jpg", _leaf_jpeg(), "image/jpeg")},
                    data={"demo_scenario": "clear"}).json()
    out = client.post(f"/api/followups/{r['followup']['id']}", data={"response": "got_worse"}).json()

    with SessionLocal() as db:
        bundle = services.case_bundle(db, kb_for_tests(), db.get(Case, out["case"]["id"]))
    assert any("without a photograph" in o["answer"] for o in bundle["farmer_report"])
    assert bundle["photos"] == [] or len(bundle["photos"]) == 1


def test_a_new_season_does_not_inherit_the_last_one(client):
    """The report that forced this: harvest a field, sow it again, and the
    same old alerts, the same old problems and the same unanswered follow-ups
    were all still sitting there. The field had not started a new season — it
    had been closed and reopened wearing the last crop's clothes.

    Nothing is deleted. It stops being this season's business."""
    from app.models import Alert, FollowUp, Problem, TrapReading

    with SessionLocal() as db:
        farm = db.get(Farm, 1)
        assert farm.season_no == 1
        problem = Problem(farm_id=farm.id, status="open", target="rice_blast")
        db.add(problem)
        db.flush()
        db.add_all([
            Alert(farm_id=farm.id, target="rice_blast", trigger="weather", level="high",
                  issued_on=date.today(), reason={}, tasks={"en": ["Walk the field and look at ten plants."]}),
            FollowUp(problem_id=problem.id, due_on=date.today()),
            TrapReading(farm_id=farm.id, target="rice_stem_borer", trap_type="pheromone",
                        count=9, recorded_on=date.today()),
        ])
        db.commit()
        # The stamp is automatic: nothing above mentioned a season.
        assert db.get(Alert, 1).season_no == 1

    live = client.get("/api/farms/1/home").json()
    assert live["alerts"] and live["problems"] and live["followups_due"], "the fixture did not take"

    client.post("/api/farms/1/harvest", json={})

    closed = client.get("/api/farms/1/home").json()
    assert closed["alerts"] == [], "a harvested field was still warning about its old crop"
    assert closed["problems"] == [], "last season's problems were still live"
    assert closed["followups_due"] == [], "a question was still being asked about a crop that is gone"
    assert client.get("/api/farms/1/alerts").json() == []

    client.post("/api/farms/1/sow", json={"crop": "rice", "sowing_date": date.today().isoformat()})

    fresh = client.get("/api/farms/1/home").json()
    assert fresh["farm"]["status"] == "growing" and fresh["farm"]["das"] == 0
    assert fresh["alerts"] == [] and fresh["problems"] == [] and fresh["followups_due"] == []
    assert client.get("/api/farms/1/alerts").json() == []
    assert client.get("/api/farms/1/traps").json() == []

    # Kept, not destroyed: the field's history is the point of the field.
    with SessionLocal() as db:
        assert db.get(Farm, 1).season_no == 2
        assert db.scalars(select(Alert).where(Alert.farm_id == 1)).all(), "history was deleted"
        assert [s.season_no for s in db.get(Farm, 1).seasons] == [1]
        assert db.scalars(select(FollowUp)).all() == [], "an unanswerable follow-up was left pending"


def test_a_season_end_is_well_past_the_usual_harvest(client):
    """A standing crop must never be cut off early. Every crop's season end
    sits past the day its last stage begins, with room for a late or staggered
    picking — cotton is picked over months."""
    kb = kb_for_tests()
    for crop, c in kb.crops.items():
        assert kb.season_ends(crop) > c["stages"][-1]["das"][0], crop


def test_a_farmer_can_delete_a_field_and_its_history(client):
    """The escape hatch for the copies a farmer made before they knew about
    sowing again. It takes the field's own rows with it and leaves every other
    field alone."""
    before = {f["id"] for f in client.get("/api/farms").json()}
    client.post("/api/farms/1/diagnose", files={"image": ("x.jpg", _leaf_jpeg(), "image/jpeg")},
                 data={"demo_scenario": "clear"})

    r = client.delete("/api/farms/1")
    assert r.status_code == 204, r.text

    after = {f["id"] for f in client.get("/api/farms").json()}
    assert after == before - {1}
    assert client.get("/api/farms/1").status_code == 404
    with SessionLocal() as db:
        assert db.get(Farm, 1) is None
        assert db.scalars(select(Problem).where(Problem.farm_id == 1)).all() == []
        assert db.scalars(select(Season).where(Season.farm_id == 1)).all() == []
        assert db.get(Farm, 2) is not None, "a neighbour's field was taken too"


def test_a_harvest_cannot_predate_the_sowing(client):
    r = client.post("/api/farms/1/harvest", json={"harvested_on": "2020-01-01"})
    assert r.status_code == 422


def _pixel_bomb(w: int = 10_000, h: int = 10_000) -> bytes:
    """A tiny PNG that claims an enormous canvas.

    Sixty-nine bytes on the wire, a hundred megapixels once decoded, which is
    three hundred megabytes of memory per request. Pillow only warns at its own
    limit and decodes anyway, so nothing stops this but reading the header."""
    import struct
    import zlib

    buf = io.BytesIO()
    Image.new("RGB", (1, 1), (10, 120, 40)).save(buf, "PNG")
    raw = bytearray(buf.getvalue())
    i = raw.index(b"IHDR")
    raw[i + 4:i + 12] = struct.pack(">II", w, h)
    raw[i + 17:i + 21] = struct.pack(">I", zlib.crc32(bytes(raw[i:i + 17])) & 0xFFFFFFFF)
    return bytes(raw)


def test_a_photograph_is_refused_before_it_is_expanded(client):
    """A picture is checked by its header, not by decoding it and finding out."""
    r = client.post("/api/farms/1/diagnose", files={"image": ("bomb.png", _pixel_bomb(), "image/png")},
                    data={"lang": "en"})
    assert r.status_code == 422
    assert "could not read" in r.json()["detail"]


def test_an_oversized_upload_is_refused_without_being_held(client, monkeypatch):
    """The cap is enforced while the body arrives, not after it has all been
    read into memory — otherwise "too large" costs the memory it refuses."""
    from app.routers import farmer as farmer_router

    monkeypatch.setattr(farmer_router, "MAX_UPLOAD_BYTES", 64 * 1024)
    big = _leaf_jpeg() + b"\0" * (200 * 1024)
    r = client.post("/api/farms/1/diagnose", files={"image": ("big.jpg", big, "image/jpeg")},
                    data={"lang": "en"})
    assert r.status_code == 413
