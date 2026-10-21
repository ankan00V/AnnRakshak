"""The harvest prediction: heat, not calendar days."""
import json
from datetime import date, timedelta

from app.engine import phenology
from app.kb import get_kb


def kb_for_tests():
    return get_kb()


class Plot:
    """The few fields a prediction reads."""

    def __init__(self, crop="rice", sown_days_ago=100, lat=21.17, lon=79.65):
        self.crop = crop
        self.sowing_date = date.today() - timedelta(days=sown_days_ago)
        self.date_basis = "sown"
        self.state = "Maharashtra"
        self.lat, self.lon = lat, lon


def _cache(farm, kb, mean_c: float, days: int, today: date | None = None) -> None:
    """Pretend the sweep fetched a season of weather at this temperature."""
    today = today or date.today()
    sown = kb.sown_on(farm.crop, farm.sowing_date, farm.date_basis, farm.state)
    means = {(sown + timedelta(days=i)).isoformat(): mean_c for i in range(days)}
    phenology.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    phenology._cache_path(round(farm.lat, 2), round(farm.lon, 2), sown).write_text(
        json.dumps({"fetched_at": "2000-01-01T00:00:00+00:00", "means": means}))


def test_a_warm_season_ripens_sooner_than_a_cool_one():
    """The whole point. Two identical rice plots sown on the same day, one in
    a warm season and one in a cool one, are not ready on the same date — and
    a flat "rice is 160 days" cannot say so."""
    kb = kb_for_tests()
    warm, cool = Plot(lat=21.10, lon=79.10), Plot(lat=21.20, lon=79.20)
    _cache(warm, kb, mean_c=30.0, days=100)
    _cache(cool, kb, mean_c=22.0, days=100)

    hot = phenology.predict(kb, warm)
    cold = phenology.predict(kb, cool)
    assert hot.basis == cold.basis == "thermal"
    assert hot.on < cold.on, "the warmer field was not predicted to ripen first"


def test_a_prediction_stays_inside_the_crop_calendar():
    """A temperature series with a hole in it should move the estimate, not
    replace the agronomy. Nothing may claim rice was ready in forty days."""
    kb = kb_for_tests()
    farm = Plot(lat=22.10, lon=79.30)
    _cache(farm, kb, mean_c=45.0, days=100)  # absurd heat
    kbc = kb.crops["rice"]
    sown = kb.sown_on(farm.crop, farm.sowing_date, farm.date_basis, farm.state)

    h = phenology.predict(kb, farm)
    assert sown + timedelta(days=kbc["stages"][-1]["das"][0]) <= h.on
    assert h.on <= sown + timedelta(days=kbc["season_ends_das"])


def test_without_weather_it_says_so_and_uses_the_calendar():
    """A field nobody has swept yet gets the crop's typical duration, marked
    as the weaker answer it is — never a slow one."""
    kb = kb_for_tests()
    farm = Plot(lat=1.11, lon=1.11)  # nothing cached for this spot
    h = phenology.predict(kb, farm)
    assert h.basis == "calendar" and h.confidence == "low"


def test_the_read_path_never_goes_to_the_network(monkeypatch):
    """A farmer opening their own list must not wait on an HTTP call."""
    kb = kb_for_tests()
    farm = Plot(lat=2.22, lon=2.22)

    def boom(*a, **k):
        raise AssertionError("the read path tried to fetch")

    monkeypatch.setattr(phenology, "fetch_series", boom)
    assert phenology.predict(kb, farm).basis == "calendar"


def test_a_collapsed_canopy_beats_any_estimate():
    """The satellite watching the crop come off is worth more than predicting
    when it will."""
    kb = kb_for_tests()
    farm = Plot(sown_days_ago=150)
    sown = kb.sown_on(farm.crop, farm.sowing_date, farm.date_basis, farm.state)
    cut = sown + timedelta(days=130)
    series = ([{"on": sown + timedelta(days=d), "mean": 0.75} for d in (40, 70, 100)]
              + [{"on": cut, "mean": 0.20}, {"on": cut + timedelta(days=5), "mean": 0.18}])

    h = phenology.predict(kb, farm, ndvi=series)
    assert h.basis == "observed" and h.on == cut and h.confidence == "high"


def test_a_canopy_that_never_grew_is_not_a_harvest():
    """Bare ground all season is a failed sowing or a bad polygon, not a crop
    that was cut. Claiming a harvest from it would be a guess."""
    kb = kb_for_tests()
    farm = Plot(sown_days_ago=150)
    sown = kb.sown_on(farm.crop, farm.sowing_date, farm.date_basis, farm.state)
    flat = [{"on": sown + timedelta(days=d), "mean": 0.12} for d in (20, 50, 80, 110)]
    assert phenology.predict(kb, farm, ndvi=flat).basis != "observed"


def test_degree_days_floor_at_the_base_and_cap_at_the_top():
    """A frost does not run the clock backwards, and a 44°C May does not run
    it double."""
    cold = {date(2026, 1, i + 1): 5.0 for i in range(10)}
    hot = {date(2026, 5, i + 1): 44.0 for i in range(10)}
    assert phenology.gdd(cold, base=10.0) == 0.0
    assert phenology.gdd(hot, base=10.0, cap=35.0) == 10 * 25.0
