"""Weather rules, spray windows, water balance, notices and their delivery
(in-app, phone, email). Weather is synthetic and hour-by-hour so every rule can
be driven exactly; nothing here touches the network."""

import asyncio
import email
import email.policy
import re
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import mailer, notify, services, watch
from app.db import Base, SessionLocal, engine
from app.engine import agromet, agroweather
from app.engine.weather import Day, Window
from app.kb import get_kb
from app.main import app
from app.models import EmailLog, Farm, Notice, Problem, PushSubscription

kb = get_kb()
AM = kb.agromet
NOW = datetime(2026, 9, 15, 10, 0)  # a Tuesday, 10 am IST


def bundle(hour=None, day=None, now=NOW) -> dict:
    """Seven past and seven coming days of calm, dry, mild weather; `hour(t, row)`
    and `day(d, row)` may change any row."""
    start = datetime.combine(now.date() - timedelta(days=7), datetime.min.time())
    hours, days = [], []
    for i in range(14 * 24):
        t = start + timedelta(hours=i)
        row = {"t": t.strftime("%Y-%m-%dT%H:%M"), "temp": 27.0, "rh": 65, "dew": 19.0, "feels": 28.0,
               "precip": 0.0, "prob": 5, "code": 1, "cloud": 30, "vis": 20000, "wind": 8.0, "gust": 14.0,
               "wdir": 250, "uv": 6.0 if 9 <= t.hour <= 15 else 0.5, "et0": 0.2, "pressure": 1010.0,
               "is_day": 1 if 6 <= t.hour < 18 else 0, "soil_t0": 26.0, "soil_t6": 25.0,
               "sm0": 0.30, "sm1": 0.31, "sm3": 0.32, "sm9": 0.34}
        if hour:
            hour(t, row)
        hours.append(row)
    for k in range(14):
        d = now.date() - timedelta(days=7) + timedelta(days=k)
        row = {"on": d.isoformat(), "tmin": 22.0, "tmax": 31.0, "feels_max": 33.0, "rain": 0.0, "prob": 5,
               "rain_hours": 0, "wind_max": 12.0, "gust_max": 20.0, "wdir": 250, "uv_max": 7.0,
               "sunshine_s": 30000, "radiation": 20.0, "et0": 4.5, "code": 1, "sunrise": None, "sunset": None}
        if day:
            day(d, row)
        days.append(row)
    return {"lat": 21.17, "lon": 79.65, "fetched_at": now.isoformat(), "stale": False,
            "current": {"temp": 27.5, "feels": 29.0, "rh": 64, "precip": 0.0, "wind": 8.0, "gust": 14.0,
                        "wdir": 250, "uv": 6.0, "cloud": 30, "vis": 20000, "pressure": 1009.0, "code": 1,
                        "is_day": 1, "time": now.isoformat()},
            "hours": hours, "days": days,
            "source": {"forecast": "test", "current": "test", "soil": "test", "et0": "test"}}


def rules(b, crop="rice", stage="tillering", **kw):
    return {a["rule"]: a for a in agromet.evaluate(b, AM, crop, stage, NOW, **kw)}


def ahead(t, h0, h1):
    return NOW + timedelta(hours=h0) <= t < NOW + timedelta(hours=h1)


# --- rules ---------------------------------------------------------------------

def test_calm_dry_day_has_a_spray_window_and_no_warnings():
    r = rules(bundle(day=lambda d, row: row.update(rain=6.0) if d < NOW.date() else None))
    assert "spray_window" in r and not r["spray_window"]["notify"]
    assert not [a for a in r.values() if a["severity"] == "warning"]
    assert "irrigate" not in r  # a week of rain covered the crop's use


def test_thunderstorm_is_a_warning_with_the_hour():
    b = bundle(hour=lambda t, row: row.update(code=95, prob=70) if t == NOW.replace(hour=17) else None)
    a = rules(b)["thunderstorm"]
    assert a["severity"] == "warning" and a["key"] == f"thunderstorm:{NOW.date()}"
    assert agromet.render(a, AM, "en", "rice", NOW)["title"] == "Thunderstorm likely today 17:00"
    assert agromet.render(a, AM, "mr", "rice", NOW)["title"].startswith("आज 17:00")


def test_heavy_rain_replaces_hold_irrigation():
    tomorrow = NOW.date() + timedelta(days=1)
    b = bundle(hour=lambda t, row: row.update(precip=4.0, prob=90) if t.date() == tomorrow else None,
               day=lambda d, row: row.update(rain=96.0, prob=90) if d == tomorrow else None)
    r = rules(b)
    assert r["heavy_rain"]["values"]["mm"] == 96 and "rain_skip_irrigation" not in r
    assert "Heavy rain tomorrow: about 96 mm" == agromet.render(r["heavy_rain"], AM, "en", "rice", NOW)["title"]


def test_moderate_rain_holds_irrigation():
    b = bundle(hour=lambda t, row: row.update(precip=1.0, prob=80) if ahead(t, 20, 34) else None)
    r = rules(b)
    assert r["rain_skip_irrigation"]["values"] == {"mm": 14, "prob": 80}


def test_humid_warm_hours_flag_fungal_weather():
    b = bundle(hour=lambda t, row: row.update(rh=95, temp=24.0) if ahead(t, 0, 14) else None)
    a = rules(b)["fungal_weather"]
    assert a["values"]["hours"] == 14 and a["severity"] == "advice"


def test_heat_at_flowering_uses_the_lower_threshold():
    hot = bundle(day=lambda d, row: row.update(tmax=36.0) if d == NOW.date() + timedelta(days=1) else None)
    assert rules(hot, "rice", "flowering")["heat_crop"]["values"]["why"] == "flowering"
    assert "heat_crop" not in rules(hot, "rice", "tillering")
    very = bundle(day=lambda d, row: row.update(tmax=39.0) if d == NOW.date() else None)
    assert rules(very, "cotton", "vegetative")["heat_crop"]["values"]["why"] == "any"


def test_gusts_fog_and_frost():
    b = bundle(hour=lambda t, row: row.update(gust=52.0) if t == NOW.replace(hour=15) else
               row.update(vis=400) if t == NOW.replace(hour=13) else None)
    r = rules(b)
    assert r["strong_wind"]["values"]["gust"] == 52 and r["fog"]["values"]["vis"] == 400
    frost_night = NOW.date() + timedelta(days=1)
    f = bundle(hour=lambda t, row: row.update(cloud=5, wind=2.0) if t.date() == frost_night and t.hour < 8 else None,
               day=lambda d, row: row.update(tmin=3.0) if d == frost_night else None)
    r = rules(f)
    assert "frost" in r and "cold" not in r


def test_rain_after_a_logged_spray():
    b = bundle(hour=lambda t, row: row.update(precip=1.5, prob=90) if ahead(t, 1, 4) else None)
    spray = {"id": 7, "at": NOW - timedelta(hours=1), "product": "Mancozeb"}
    a = rules(b, sprays=[spray])["rain_after_spray"]
    assert a["key"] == "rain_after_spray:7" and a["values"]["verb"] == "future"
    txt = agromet.render(a, AM, "en", "rice", NOW)["text"]
    assert "Mancozeb at 09:00" in txt and "is expected" in txt


def test_no_spray_window_only_notifies_a_farm_with_a_problem():
    windy = bundle(hour=lambda t, row: row.update(wind=26.0, gust=40.0))
    assert rules(windy, needs_spray=True)["spray_no_window"]["notify"]
    a = rules(windy, needs_spray=False)["spray_no_window"]
    assert not a["notify"]
    assert agromet.render(a, AM, "en", "rice", NOW)["text"].startswith("Wind up to 26 km/h")


def test_spray_hours_explain_themselves():
    b = bundle(hour=lambda t, row: row.update(prob=70) if ahead(t, 2, 3) else None)
    hours = agromet.spray_hours(b, NOW, AM["spray"], horizon=6)
    assert hours[0]["status"] == "avoid" and hours[0]["reasons"][0][0] == "rain"  # rain within the rain-free period
    assert hours[4]["status"] == "good"


def test_water_balance_asks_for_irrigation_in_a_dry_week_but_not_at_maturity():
    b = bundle()  # no rain for a week, ET0 4.5 mm/day
    r = rules(b, "maize", "silking")
    assert r["irrigate"]["values"]["deficit"] == round(4.5 * 7 * 1.2)
    assert "irrigate" not in rules(b, "maize", "maturity")
    wb = agromet.water_balance(b, NOW.date(), 0.5, AM["thresholds"], "maize", stop=True)
    assert wb["verdict"] == "stop_stage"


def test_every_rule_renders_in_every_language():
    b = bundle()
    fake_values = {
        "thunderstorm": {"when": "2026-09-15T17:00"}, "heavy_rain": {"day": "2026-09-16", "mm": 80},
        "strong_wind": {"when": "2026-09-15T15:00", "gust": 50}, "frost": {"day": "2026-09-16", "tmin": 3},
        "rain_after_spray": {"product": None, "time": "09:00", "mm": 3.1, "hours": 6, "verb": "past"},
        "heat_crop": {"day": "2026-09-16", "tmax": 36, "why": "flowering"},
        "fungal_weather": {"hours": 20, "tmin": 22, "tmax": 27},
        "spray_no_window": {"reasons": [["rain", 70], ["calm", None]]},
        "rain_skip_irrigation": {"mm": 14, "prob": 80}, "irrigate": {"etc": 30, "rain": 2, "deficit": 28},
        "heat_people": {"day": "2026-09-15", "uv": 9, "tmax": 37, "feels": 42}, "cold": {"day": "2026-09-16", "tmin": 8},
        "fog": {"when": "2026-09-16T06:00", "vis": 300},
        "spray_window": {"start": "2026-09-15T16:00", "end": "2026-09-15T18:00", "wind": 7},
        "greenness_drop": {"before": 0.71, "after": 0.55, "d1": "2026-09-01", "d2": "2026-09-11", "source": "Sentinel-2"},
    }
    assert set(fake_values) == {r["id"] for r in AM["rules"]}
    for rid, values in fake_values.items():
        rule = next(r for r in AM["rules"] if r["id"] == rid)
        adv = {"rule": rid, "severity": rule["severity"], "category": rule["category"], "notify": rule["notify"],
               "key": rid, "values": values, "valid_until": "2026-09-16T00:00"}
        for lang in ("en", "hi", "mr"):
            r = agromet.render(adv, AM, lang, "rice", NOW)
            assert r["title"] and r["text"] and r["do"]
            assert not re.search(r"[{}]", r["title"] + r["text"]), (rid, lang)
    assert b  # the builder itself is sound


def test_view_has_every_parameter_the_farmer_asked_for():
    v = agromet.view(bundle(), AM, "rice", "flowering", NOW, "en")
    for k in ("temp", "feels", "rh", "dew", "precip", "prob_3h", "wind", "gust", "wdir", "uv", "uv_band",
              "cloud", "vis", "pressure", "pressure_trend_24h"):
        assert k in v["current"], k
    assert len(v["hourly"]) == 48 and len(v["daily"]) == 7
    assert {"rain", "prob", "gust_max", "uv_max", "sunshine_h", "et0"} <= set(v["daily"][0])
    assert v["soil"]["moisture"][3]["pct"] == 34 and v["water"]["available"]
    assert v["current"]["pressure_trend_24h"] == -1.0


# --- sources --------------------------------------------------------------------

def test_hargreaves_matches_fao56():
    # FAO-56 Example 8: 20° S on 3 September -> Ra = 32.2 MJ m-2 day-1
    assert agroweather.extraterrestrial_radiation(-20, 246) == pytest.approx(32.2, abs=0.2)
    # Nagpur in mid-September, 24/31 °C: Open-Meteo's Penman-Monteith said ~4.2 mm
    assert agroweather.hargreaves_et0(24, 31, 21.15, 258) == pytest.approx(4.2, abs=0.6)


def test_openweather_forecast_fallback_parses_to_hours_and_days():
    ts = int(datetime(2026, 9, 15, 12, 0, tzinfo=agroweather.IST).timestamp())
    payload = {"list": [{"dt": ts + 3 * 3600 * i, "main": {"temp": 28 + i, "feels_like": 31, "humidity": 80,
                                                           "pressure": 1008},
                         "wind": {"speed": 3.0, "deg": 200, "gust": 6.0}, "visibility": 9000, "pop": 0.6,
                         "rain": {"3h": 3.0}, "clouds": {"all": 75}, "weather": [{"id": 501}], "sys": {"pod": "d"}}
                        for i in range(8)]}
    hours, days = agroweather.parse_owm_forecast(payload, 21.17)
    assert len(hours) == 24 and hours[0]["t"] == "2026-09-15T10:00" and hours[0]["precip"] == 1.0
    assert hours[0]["wind"] == 10.8 and hours[0]["prob"] == 60 and hours[0]["code"] == 63
    assert days[0]["et0"] > 0 and days[0]["rain"] == pytest.approx(sum(h["precip"] for h in hours if h["t"].startswith("2026-09-15")))
    assert agroweather.owm_code(211) == 95 and agroweather.owm_code(741) == 45 and agroweather.owm_code(800) == 0


# --- notices and delivery ------------------------------------------------------

@pytest.fixture()
def world(monkeypatch):
    calm_window = Window([Day(date.today() - timedelta(6 - i), 60, 22, 31, 0.0) for i in range(10)], "test", datetime.now())
    monkeypatch.setattr(services, "fetch_window", lambda lat, lon: calm_window)
    monkeypatch.setattr(services, "fetch_month_rain", lambda lat, lon: None)
    sent = []

    def fake_webpush(sub, data, **kw):
        sent.append((sub["endpoint"], data))
        if "gone" in sub["endpoint"]:
            from pywebpush import WebPushException

            class R:
                status_code = 410
            raise WebPushException("gone", response=R())

    monkeypatch.setattr(notify, "webpush", fake_webpush)
    monkeypatch.setattr(notify.live, "soil_ph_for", lambda db, farm, lat, lon, lang: {
        "value": 7.4, "how": "estimated", "band": "neutral", "source": "test"})
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:
        with SessionLocal() as db:
            db.add(Farm(farmer_name="Sunita", crop="rice", sowing_date=NOW.date() - timedelta(days=80),
                        district="Bhandara", lat=21.17, lon=79.65, area_acres=2, lang="mr"))
            db.commit()
        yield c, sent


def storm(t, row):
    if t == NOW.replace(hour=17):
        row.update(code=95, prob=80)


def humid(t, row):
    if ahead(t, 0, 14):
        row.update(rh=95, temp=24.0)


def run(b, now=NOW):
    return watch.cycle(now=now, fetch=lambda lat, lon: b)


def test_watch_issues_each_notice_once(world):
    b = bundle(hour=lambda t, row: (storm(t, row), humid(t, row)))
    first = run(b)
    again = run(b)
    assert first["notices"] >= 2 and again.get("notices", 0) == 0
    with SessionLocal() as db:
        rules_ = {n.rule for n in db.query(Notice).all()}
    assert {"thunderstorm", "fungal_weather"} <= rules_


def test_phone_gets_warnings_at_night_and_advice_waits_for_morning(world):
    c, sent = world
    c.post("/api/farms/1/push/subscribe", json={"endpoint": "https://fcm.googleapis.com/fcm/send/abc",
                                                "keys": {"p256dh": "B" * 60, "auth": "a" * 16}})
    night = NOW.replace(hour=23)
    b = bundle(now=night, hour=lambda t, row: (row.update(code=95, prob=80) if t == night.replace(hour=23) + timedelta(hours=2) else None,
                                               row.update(rh=95, temp=24.0) if night <= t < night + timedelta(hours=14) else None))
    watch.cycle(now=night, fetch=lambda lat, lon: b)
    titles = [d for _, d in sent]
    assert len(titles) == 1 and "वादळी" in titles[0]  # the storm, in Marathi; fungal advice held
    watch.cycle(now=night + timedelta(hours=8), fetch=lambda lat, lon: b)  # 07:00
    assert any("बुरशी" in d for _, d in sent[1:])  # held advice goes out in the morning


def test_gone_phone_is_forgotten(world):
    c, sent = world
    c.post("/api/farms/1/push/subscribe", json={"endpoint": "https://fcm.googleapis.com/fcm/send/gone",
                                                "keys": {"p256dh": "B" * 60, "auth": "a" * 16}})
    assert c.post("/api/farms/1/push/test").json()["removed"] == 1
    with SessionLocal() as db:
        assert db.query(PushSubscription).count() == 0


def test_warning_email_right_away_and_one_summary_a_day(world):
    c, _ = world
    assert c.put("/api/farms/1/contact", json={"email": "not-an-email"}).status_code == 422
    r = c.put("/api/farms/1/contact", json={"email": "sunita@example.in", "email_pref": "warnings"}).json()
    assert r["email"] == "sunita@example.in" and r["email_delivery"] == "outbox"
    b = bundle(hour=lambda t, row: (storm(t, row), humid(t, row)))
    stats = run(b)
    assert stats["alert_emails"] == 1 and stats["digests"] == 1
    assert run(b).get("digests", 0) == 0  # once per day
    with SessionLocal() as db:
        logs = db.query(EmailLog).order_by(EmailLog.id).all()
        assert [x.kind for x in logs] == ["alert", "digest"] and all(x.status == "outbox" for x in logs)
        # 'warnings' mode: the fungal advice is not emailed on its own, only the storm
        assert logs[0].subject.startswith("⚠") and "वादळी" in logs[0].subject
    msgs = [email.message_from_bytes(f.read_bytes(), policy=email.policy.default) for f in mailer.OUTBOX.glob("*.eml")]
    digest = next(m for m in msgs if "आज तुमचे भात शेत" in m["Subject"])
    assert digest["List-Unsubscribe"] and "Sunita" in digest.get_body(("plain",)).get_content()
    body = digest.get_body(("plain",)).get_content()
    assert "सामू (pH) 7.4" in body and "हवामान" in body  # pH and the weather rules, in Marathi


def test_unsubscribe_link_turns_emails_off(world):
    c, _ = world
    c.put("/api/farms/1/contact", json={"email": "sunita@example.in"})
    with SessionLocal() as db:
        token = db.get(Farm, 1).email_token
    assert "any more" in c.get(f"/api/email/unsubscribe?token={token}").text
    assert c.get("/api/farms/1/contact").json()["email_pref"] == "off"
    assert "expired" in c.get("/api/email/unsubscribe?token=nope").text


def test_weather_endpoint_and_spray_log(world, monkeypatch):
    c, _ = world
    b = bundle(hour=humid)
    monkeypatch.setattr(agroweather, "bundle", lambda lat, lon: b)
    monkeypatch.setattr(agroweather, "now_ist", lambda: NOW)
    v = c.get("/api/farms/1/weather?lang=hi").json()
    assert v["crop"]["stage"] == "flowering" and v["crop"]["kc"] == 1.2
    assert any(a["rule"] == "fungal_weather" for a in v["advisories"])
    s = c.post("/api/farms/1/sprays?lang=en", json={"product": "Tricyclazole"}).json()
    assert s["check"]["status"] in ("good", "caution", "avoid")
    with SessionLocal() as db:
        db.add(Problem(farm_id=1, target="rice_blast", status="open"))
        db.commit()
    run(b)
    n = c.get("/api/farms/1/notices?lang=en").json()
    assert n["unread"] >= 1 and n["items"][0]["title"]
    assert c.post("/api/farms/1/notices/read", json={}).json()["marked"] >= 1
    assert c.get("/api/farms/1/notices").json()["unread"] == 0


def test_broker_delivers_across_threads():
    async def main():
        q = notify.broker.subscribe(99)
        await asyncio.get_running_loop().run_in_executor(None, notify.broker.publish, 99, {"type": "notice", "id": 1})
        ev = await asyncio.wait_for(q.get(), 1)
        notify.broker.unsubscribe(99, q)
        return ev
    assert asyncio.run(main())["id"] == 1


def test_push_key_is_a_p256_point(world):
    c, _ = world
    import base64
    k = c.get("/api/push/key").json()["public_key"]
    raw = base64.urlsafe_b64decode(k + "=" * (-len(k) % 4))
    assert len(raw) == 65 and raw[0] == 4


# --- satellite (NDVI) ----------------------------------------------------------

def _scene(day: str, mean: float, cloud: int = 5, cover: int = 100, kind: str = "s2") -> dict:
    ts = int(datetime.fromisoformat(day + "T05:30:00").timestamp())
    return {"dt": ts, "type": kind, "cl": cloud, "dc": cover, "data": {"mean": mean, "p25": mean - .05, "p75": mean + .05}}


def test_cloudy_scenes_never_count():
    from app.engine import satellite
    rows = [_scene("2026-09-01", 0.70), _scene("2026-09-05", 0.20, cloud=90), _scene("2026-09-07", 0.25, cover=40),
            _scene("2026-09-09", 0.72, kind="l8")]
    s = satellite.parse_history(rows)
    assert [x["on"] for x in s] == ["2026-09-01", "2026-09-09"] and s[1]["source"] == "Landsat 8"


def test_a_greenness_drop_is_a_notice_but_not_while_ripening():
    from app.engine import satellite
    today = date.today()
    series = [{"on": (today - timedelta(days=12)).isoformat(), "mean": 0.72, "p25": 0.7, "p75": 0.75, "source": "Sentinel-2", "cloud": 3},
              {"on": (today - timedelta(days=2)).isoformat(), "mean": 0.55, "p25": 0.5, "p75": 0.6, "source": "Sentinel-2", "cloud": 8}]
    s = satellite.summarize(series, "rice", "flowering", today)
    assert s["drop"] and s["change"] == -0.17 and s["band"] == "moderate"
    adv = satellite.evaluate(s, NOW)
    assert adv["rule"] == "greenness_drop" and adv["values"]["before"] == 0.72
    r = agromet.render(adv, AM, "en", "rice", NOW)
    assert "0.72 → 0.55" in r["title"] and "Sentinel-2" in r["text"]
    assert not satellite.summarize(series, "rice", "maturity", today)["drop"]  # ripening: NDVI falls anyway
    assert satellite.evaluate(satellite.summarize(series[:1], "rice", "flowering"), NOW) is None


def test_field_polygon_is_the_farm_area_but_never_below_the_minimum():
    import math

    from app.engine import satellite
    ring = satellite.square(21.17, 79.65, 0.4)["geometry"]["coordinates"][0]
    side_m = (ring[2][1] - ring[0][1]) * 111_320
    assert ring[0] == ring[-1] and math.isclose(side_m ** 2 / 10_000, satellite.MIN_HA, rel_tol=0.01)


def test_watch_creates_the_polygon_once_and_issues_a_greenness_notice(world, monkeypatch):
    from app.engine import satellite
    monkeypatch.setattr(satellite, "configured", lambda: True)
    made = []
    monkeypatch.setattr(satellite, "create_polygon", lambda name, lat, lon, ha: made.append(name) or {"id": "poly-1"})
    today = NOW.date()
    monkeypatch.setattr(satellite, "ndvi_series", lambda pid, d: [
        {"on": (today - timedelta(days=11)).isoformat(), "mean": 0.74, "p25": 0.7, "p75": 0.8, "source": "Sentinel-2", "cloud": 2},
        {"on": (today - timedelta(days=1)).isoformat(), "mean": 0.58, "p25": 0.5, "p75": 0.6, "source": "Sentinel-2", "cloud": 4}])
    stats = run(bundle())
    run(bundle())
    assert made == ["annrakshak-farm-1"] and stats["satellite"] == 1
    with SessionLocal() as db:
        n = db.query(Notice).filter(Notice.rule == "greenness_drop").one()
        assert db.get(Farm, 1).agro_polygon_id == "poly-1" and n.values["after"] == 0.58


def test_a_subscription_may_only_point_at_a_push_service(world):
    """An endpoint is a URL this server posts to later, by itself, from inside
    whatever network it runs in. Unchecked, "subscribe me" is a request to make
    the server fetch an address of the caller's choosing."""
    c, _ = world
    keys = {"p256dh": "B" * 60, "auth": "a" * 16}
    for bad in ("https://10.0.0.5/steal", "https://169.254.169.254/latest/meta-data/",
                "https://evil.example.com/hook"):
        r = c.post("/api/farms/1/push/subscribe", json={"endpoint": bad, "keys": keys})
        assert r.status_code == 422, f"{bad} was accepted"
    with SessionLocal() as db:
        assert db.query(PushSubscription).count() == 0

    for good in ("https://fcm.googleapis.com/fcm/send/abc",
                 "https://updates.push.services.mozilla.com/wpush/v2/abc",
                 "https://web.push.apple.com/abc"):
        assert c.post("/api/farms/1/push/subscribe",
                      json={"endpoint": good, "keys": keys}).status_code == 201
    with SessionLocal() as db:
        assert db.query(PushSubscription).count() == 3
