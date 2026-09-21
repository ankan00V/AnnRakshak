"""INSAT-3DS satellite rain via MOSDAC: reading a granule, one ingest cycle
against a stand-in MOSDAC, and observed rain replacing modelled rain."""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta, timezone

import h5py
import httpx
import numpy as np
import pytest

from app import mosdac
from app.db import Base, SessionLocal, engine
from app.engine import agroweather
from app.engine.weather import Day, Window, merge_rain
from app.models import Farm, SatRain

BHANDARA = (21.17, 79.65)


def granule(rate_at_bhandara: float, path=None):
    """A small granule laid out like the product: 2-D Latitude/Longitude and a
    scaled integer HEM layer with a fill value."""
    lat = np.linspace(22.0, 20.0, 41)
    lon = np.linspace(79.0, 81.0, 41)
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    hem = np.zeros((1, 41, 41), dtype="int16")
    i, j = int(np.argmin(np.abs(lat - BHANDARA[0]))), int(np.argmin(np.abs(lon - BHANDARA[1])))
    hem[0, i, j] = int(round(rate_at_bhandara * 10))
    hem[0, 0, 0] = -999
    buf = path or io.BytesIO()
    with h5py.File(buf, "w") as f:
        g = f.create_group("geo")
        for name, arr in (("Latitude", la), ("Longitude", lo)):
            d = g.create_dataset(name, data=(arr * 100).astype("int16"))
            d.attrs["scale_factor"] = 0.01
        d = f.create_dataset("HEM", data=hem)
        d.attrs["scale_factor"] = 0.1
        d.attrs["_FillValue"] = -999
    return buf


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as s:
        s.add(Farm(farmer_name="t", crop="rice", sowing_date=date(2026, 7, 1), district="Bhandara",
                   lat=BHANDARA[0], lon=BHANDARA[1], area_acres=1))
        s.commit()
        yield s


def test_reads_the_rain_rate_at_the_farm(tmp_path):
    p = tmp_path / "g.h5"
    granule(12.5, p)
    rates = mosdac.read_rain(p, [BHANDARA, (21.9, 79.6), (30.0, 75.0)])
    assert rates[0] == 12.5          # the farm's pixel, scale applied
    assert rates[1] == 0.0           # dry pixel
    assert rates[2] is None          # off this image: no pixel close enough


def test_an_unknown_layout_is_an_error_not_a_zero(tmp_path):
    p = tmp_path / "odd.h5"
    with h5py.File(p, "w") as f:
        f.create_dataset("something", data=np.zeros(3))
    with pytest.raises(ValueError, match="unrecognised"):
        mosdac.read_rain(p, [BHANDARA])


def _fake_mosdac(now: datetime, rates: dict[int, float], calls: list[str]):
    """Stand-in MOSDAC: one granule every 30 min for the last `len(rates)` slots."""
    entries = []
    for n in rates:
        t = (now - timedelta(minutes=30 * n)).replace(second=0, microsecond=0)
        entries.append({"id": str(1000 + n), "identifier": f"g{n}.h5",
                        "updated": t.strftime("%Y-%m-%dT%H:%M:%SZ")})

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path.endswith("/datasets.json"):
            return httpx.Response(200, json={"totalResults": len(entries), "entries": entries})
        if req.url.path.endswith("/gettoken"):
            return httpx.Response(200, json={"access_token": "tok", "refresh_token": "r"})
        if req.url.path.endswith("/download"):
            assert req.headers["authorization"] == "Bearer tok"
            n = int(req.url.params["id"]) - 1000
            return httpx.Response(200, content=granule(rates[n]).getvalue())
        if req.url.path.endswith("/logout"):
            return httpx.Response(200, json={})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_one_cycle_stores_the_rain_and_skips_what_it_has(db, monkeypatch):
    monkeypatch.setattr(mosdac, "MOSDAC_USERNAME", "u")
    monkeypatch.setattr(mosdac, "MOSDAC_PASSWORD", "p")
    monkeypatch.setattr(mosdac, "_state", dict(mosdac._state, locked_out=False))
    now = datetime.now(timezone.utc)
    calls: list[str] = []
    out = mosdac.ingest(db, now, client=_fake_mosdac(now, {1: 4.0, 2: 2.0, 3: 0.0}, calls))
    assert out == {"found": 3, "fetched": 3, "stored": 3}
    assert db.query(SatRain).count() == 3
    assert calls.count("/download_api/download") == 3 and "/download_api/logout" in calls

    again: list[str] = []
    out = mosdac.ingest(db, now, client=_fake_mosdac(now, {1: 4.0, 2: 2.0, 3: 0.0}, again))
    assert out["fetched"] == 0 and "/download_api/gettoken" not in again  # nothing new: no login

    last = mosdac.last_24h(db, *BHANDARA, now=now)
    assert last["mm"] == 48.0 and last["source"].startswith("INSAT-3DS")  # mean 2 mm/h x 24 h


def test_a_refused_login_is_not_retried(db, monkeypatch):
    monkeypatch.setattr(mosdac, "MOSDAC_USERNAME", "u")
    monkeypatch.setattr(mosdac, "MOSDAC_PASSWORD", "wrong")
    monkeypatch.setattr(mosdac, "_state", dict(mosdac._state, locked_out=False))
    now = datetime.now(timezone.utc)

    def handler(req):
        if req.url.path.endswith("/datasets.json"):
            return httpx.Response(200, json={"totalResults": 1, "entries": [
                {"id": "1", "identifier": "g.h5", "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ")}]})
        return httpx.Response(401, json={"error": "Invalid Username/Password"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert "error" in mosdac.ingest(db, now, client=client)
    assert mosdac.ingest(db, now, client=client) == {"skipped": "login refused"}  # three strikes lock the account


def test_without_an_account_nothing_is_fetched(db, monkeypatch):
    monkeypatch.setattr(mosdac, "MOSDAC_USERNAME", None)
    assert mosdac.ingest(db) == {"skipped": "not configured"}


def test_observed_rain_replaces_the_models_only_for_well_covered_past_days(db):
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    full, thin = date(2026, 9, 19), date(2026, 9, 20)
    for k in range(48):  # every slot of the 19th (IST), 1 mm/h
        db.add(SatRain(dataset=mosdac.MOSDAC_DATASET, lat=21.17, lon=79.65, mm_h=1.0,
                       slot=datetime(2026, 9, 18, 18, 30, tzinfo=timezone.utc) + timedelta(minutes=30 * k)))
    for k in range(6):  # six slots of the 20th
        db.add(SatRain(dataset=mosdac.MOSDAC_DATASET, lat=21.17, lon=79.65, mm_h=9.0,
                       slot=datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=30 * k)))
    db.commit()
    days = mosdac.observed_days(db, *BHANDARA, now=now)
    assert days[full] == {"mm": 24.0, "coverage": 1.0}
    assert days[thin]["coverage"] < mosdac.MIN_COVERAGE
    assert mosdac.trusted(days) == {full: 24.0}

    w = Window([Day(full, 90, 22, 30, 0.0), Day(thin, 90, 22, 30, 3.0)], "model", now)
    merged = merge_rain(w, mosdac.trusted(days))
    assert [d.rain_mm for d in merged.days] == [24.0, 3.0]


def test_the_weather_bundle_carries_observed_rain_without_editing_the_cache(db, monkeypatch):
    today = agroweather.now_ist().date()
    y = today - timedelta(days=1)
    cached = {"days": [{"on": y.isoformat(), "rain": 0.0}, {"on": today.isoformat(), "rain": 0.0}]}
    monkeypatch.setattr(mosdac, "observed_days", lambda db, lat, lon: {y: {"mm": 17.0, "coverage": 0.9}})
    monkeypatch.setattr(mosdac, "last_24h", lambda db, lat, lon: {"mm": 17.0})
    out = agroweather.with_observed_rain(cached, *BHANDARA)
    assert out["days"][0] == {"on": y.isoformat(), "rain": 17.0, "rain_src": "satellite"}
    assert out["days"][1]["rain"] == 0.0            # today is still the forecast's
    assert cached["days"][0]["rain"] == 0.0          # the shared cached copy is untouched
    assert out["sat_rain"] == {"mm": 17.0}
