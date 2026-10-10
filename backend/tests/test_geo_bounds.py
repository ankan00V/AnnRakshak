"""A place name from a geocoder cannot be longer than the farm can hold.

`reverse()` and `search()` return names from someone else's database --
BigDataCloud, Nominatim, Open-Meteo -- and `reverse()`'s answer is written
straight into farm.state, farm.district and farm.village when a farmer
confirms that their field really is where the phone says. Nothing bounded
those names, so a long one was a failed write on the farmer's own screen, in
the same way a long model name was a failed write on every photo upload.

A name that does not fit is dropped, not cut. Half a village's name is a
different village, and the column it would fill already holds either the
farmer's own answer or nothing.
"""

import httpx
import pytest

from app import cache, geo

LONG = "Sri " + "Venkata " * 12 + "Puram"   # 105 characters, longer than any column here


@pytest.fixture(autouse=True)
def _no_cached_answers(monkeypatch):
    """geo caches every lookup for a month; these tests must see the fetch."""
    monkeypatch.setattr(cache, "get_json", lambda *a, **k: None)
    monkeypatch.setattr(cache, "set_json", lambda *a, **k: None)


def test_the_limits_are_the_ones_the_module_publishes():
    assert len(LONG) > max(geo.PLACE_LIMITS.values())


def test_a_long_village_from_a_reverse_lookup_is_dropped(monkeypatch):
    monkeypatch.setattr(geo, "_big_data_cloud",
                        lambda c, lat, lon: {"state": "Maharashtra", "district": "Bhandara", "village": LONG})
    out = geo.reverse(21.17, 79.65)
    assert out["district"] == "Bhandara"      # the parts that fit still arrive
    assert out["state"] == "Maharashtra"
    assert out["village"] is None             # and the one that does not is simply unknown


def test_a_long_district_from_a_reverse_lookup_is_dropped(monkeypatch):
    monkeypatch.setattr(geo, "_big_data_cloud",
                        lambda c, lat, lon: {"state": LONG, "district": LONG, "village": "Sakoli"})
    out = geo.reverse(21.17, 79.65)
    assert (out["state"], out["district"]) == (None, None)
    assert out["village"] == "Sakoli"


def test_a_name_that_fits_is_untouched(monkeypatch):
    monkeypatch.setattr(geo, "_big_data_cloud",
                        lambda c, lat, lon: {"state": "Maharashtra", "district": "Bhandara", "village": "Sakoli"})
    assert geo.reverse(21.17, 79.65) == {"state": "Maharashtra", "district": "Bhandara", "village": "Sakoli"}


def test_a_search_hit_the_form_could_not_accept_is_not_offered(monkeypatch):
    """The sign-up form caps these fields too, so offering a place that cannot
    be submitted is a dead end rather than a crash -- still not worth showing.
    """
    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"results": [
                {"name": LONG, "country_code": "IN", "admin1": "Maharashtra", "admin2": "Bhandara",
                 "admin3": "Sakoli", "latitude": 21.1, "longitude": 79.6},
                {"name": "Sakoli", "country_code": "IN", "admin1": "Maharashtra", "admin2": "Bhandara",
                 "admin3": LONG, "latitude": 21.2, "longitude": 79.7},
            ]}

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, *a, **k): return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    hits = geo.search("sakoli")

    assert [h["name"] for h in hits] == ["Sakoli"]   # the unusable one is gone
    assert hits[0]["taluka"] is None                 # its over-long taluka is dropped, the hit kept
    assert hits[0]["district"] == "Bhandara"
