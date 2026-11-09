"""What must be true before this faces a farmer.

`config.start_checks` is the whole of the difference between a laptop and
production: a laptop logs the list and carries on, a process that says it is
production refuses to start on it. That makes the list itself the security
boundary, so each item is worth a test — a check quietly dropped would never
show up as a failure anywhere else.
"""

from __future__ import annotations

import pytest

from app import config


@pytest.fixture()
def safe(monkeypatch):
    """A configuration with nothing wrong with it, to vary one thing at a time."""
    monkeypatch.setattr(config, "DEMO_LOGIN", False)
    monkeypatch.setattr(config, "EXPERT_AUTO_VERIFY", False)
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    monkeypatch.setattr(config, "DB_URL", "postgresql+psycopg://user@host/annrakshak")
    monkeypatch.setattr(config, "PUBLIC_APP_URL", "https://annrakshak.in")
    monkeypatch.setattr(config, "EMAIL_BACKEND", "ses")
    monkeypatch.setattr(config, "TURNSTILE_SECRET", "0xAREALSECRETFROMCLOUDFLARE")
    return monkeypatch


def test_a_sound_configuration_has_nothing_to_say(safe):
    assert config.start_checks() == []


@pytest.mark.parametrize("attr,value,expect", [
    ("DEMO_LOGIN", True, "DEMO_LOGIN"),
    ("EXPERT_AUTO_VERIFY", True, "EXPERT_AUTO_VERIFY"),
    ("COOKIE_SECURE", False, "COOKIE_SECURE"),
    ("DB_URL", "sqlite:///./annrakshak.db", "SQLite"),
    ("PUBLIC_APP_URL", "http://localhost:5173", "PUBLIC_URL"),
    ("EMAIL_BACKEND", "outbox", "EMAIL_BACKEND"),
])
def test_each_setting_is_caught_on_its_own(safe, attr, value, expect):
    safe.setattr(config, attr, value)
    problems = config.start_checks()
    assert len(problems) == 1
    assert expect in problems[0]


@pytest.mark.parametrize("secret", sorted(config.TURNSTILE_TEST_SECRETS))
def test_every_cloudflare_test_secret_is_refused(safe, secret):
    """Not just the one that always passes.

    "Always fails" and "already spent" are no better: the answer was decided
    before the request arrived, so the box is theatre either way — and one of
    them locks every real person out instead of letting every script in.
    """
    safe.setattr(config, "TURNSTILE_SECRET", secret)
    problems = config.start_checks()
    assert len(problems) == 1
    assert "TURNSTILE_SECRET" in problems[0]


def test_a_real_turnstile_secret_passes(safe):
    safe.setattr(config, "TURNSTILE_SECRET", "0x4AAAAAAABsomethingrealfromthedashboard")
    assert config.start_checks() == []


def test_turnstile_switched_off_entirely_is_not_flagged(safe):
    """An empty secret takes the box away, which is a decision, not an accident.

    The failure this check is about is the opposite: a box that is shown, is
    answered, goes to Cloudflare and comes back a tick, and refuses nobody.
    """
    safe.setattr(config, "TURNSTILE_SECRET", "")
    assert config.start_checks() == []


def test_the_default_shipped_in_the_repository_is_one_of_the_refused_keys():
    """A deploy that forgets the variable has to be caught, not let through.

    The default lives in the source rather than the environment, so this reads
    it from there — the running process may have been handed a real key.
    """
    import ast
    import pathlib

    source = pathlib.Path(config.__file__).read_text()
    tree = ast.parse(source)
    default = next(
        node.value.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and getattr(node.targets[0], "id", None) == "TURNSTILE_SECRET"
    )

    assert default in config.TURNSTILE_TEST_SECRETS
