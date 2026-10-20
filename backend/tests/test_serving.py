"""What this process serves besides the API: the built app, and the photographs.

Both are production behaviour that no test covered: the single-page app's own
routes must survive a cold load, and a path must not walk out of the web root.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def served(tmp_path):
    """A built app on disk, and an app told to serve it."""
    from fastapi import FastAPI

    from app.main import mount_web

    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>AnnRakshak</title>")
    (web / "assets" / "app.js").write_text("console.log('hi')")
    (web / "manifest.webmanifest").write_text('{"name":"AnnRakshak"}')
    (tmp_path / "secret.txt").write_text("not for the web")

    probe = FastAPI()
    mount_web(probe, web)
    with TestClient(probe) as c:
        yield c


def test_a_deep_link_into_the_app_serves_the_shell(served):
    r = served.get("/officer/queue")
    assert r.status_code == 200 and "AnnRakshak" in r.text
    assert r.headers["cache-control"] == "no-store"   # a deploy must reach an old phone


def test_a_real_file_beside_the_shell_is_served_as_itself(served):
    assert served.get("/manifest.webmanifest").json()["name"] == "AnnRakshak"


def test_a_path_cannot_walk_out_of_the_web_root(served):
    for attempt in ("../secret.txt", "..%2fsecret.txt", "assets/../../secret.txt"):
        r = served.get(f"/{attempt}")
        assert "not for the web" not in r.text


def test_a_missing_asset_is_a_404_and_not_the_shell(served):
    """A relative asset base once made a two-level route ask for
    /signup/assets/index.js. Answering that with index.html is how a blank page
    happens: the browser refuses the MIME type and the real cause is three
    steps away."""
    r = served.get("/signup/assets/index-abc123.js")
    assert r.status_code == 404
    assert "AnnRakshak" not in r.text

    # A route with a dot in it is still a route, not a file.
    assert served.get("/officer/queue").status_code == 200


def test_health_says_little_in_production(monkeypatch):
    """/health is the one route with no session in front of it, so whatever it
    prints, it prints to the internet. A container needs "ok" and whether the
    real model is loaded; which providers are wired up, which satellite product
    is read and what it said when it last failed are a map, not a status."""
    from fastapi.testclient import TestClient

    from app import main

    with TestClient(main.app) as c:
        full = c.get("/health").json()
        assert {"kb", "satellite_rain"} <= set(full), "a laptop still prints everything"

        monkeypatch.setattr(main, "PROD", True)
        terse = c.get("/health").json()
    assert terse["status"] == "ok"
    assert set(terse) == {"status", "service", "model", "voice"}
    assert set(terse["model"]) == {"is_stub"} and set(terse["voice"]) == {"configured"}
