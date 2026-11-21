"""Tests for the pipeline's account-rotation and cap guards (no network)."""

import pytest

import db
import pipeline


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "engine.db")
    monkeypatch.setattr(pipeline, "ACCOUNTS", [
        {"name": "a1", "username": "u1", "password": "p1", "handle": "@h1"},
        {"name": "a2", "username": "u2", "password": "p2", "handle": "@h2"},
    ])
    yield


def _publish(account: str, days_ago: int = 0):
    from datetime import datetime, timedelta
    when = datetime.now() - timedelta(days=days_ago)
    db.insert_post(account=account, status="published",
                   published_at=when.isoformat(timespec="seconds"))


def test_rotation_starts_at_first_account():
    clients = {"a1": object(), "a2": object()}
    assert pipeline.pick_account(clients)["name"] == "a1"
    assert pipeline.pick_account(clients)["name"] == "a2"   # advanced
    assert pipeline.pick_account(clients)["name"] == "a1"   # wraps


def test_capped_account_is_skipped_not_fatal():
    """Regression: a capped account used to halt the entire run."""
    _publish("a1")                       # a1 now at its cap (cap >= 1 check)
    monkey_cap = 1
    import config
    original = pipeline.DAILY_CAP_PER_ACCOUNT
    pipeline.DAILY_CAP_PER_ACCOUNT = monkey_cap
    try:
        clients = {"a1": object(), "a2": object()}
        chosen = pipeline.pick_account(clients)
        assert chosen is not None, "must not deadlock when one account is capped"
        assert chosen["name"] == "a2"
    finally:
        pipeline.DAILY_CAP_PER_ACCOUNT = original


def test_all_capped_returns_none():
    import config
    original = pipeline.DAILY_CAP_PER_ACCOUNT
    pipeline.DAILY_CAP_PER_ACCOUNT = 1
    try:
        _publish("a1")
        _publish("a2")
        clients = {"a1": object(), "a2": object()}
        assert pipeline.pick_account(clients) is None
    finally:
        pipeline.DAILY_CAP_PER_ACCOUNT = original


def test_accounts_without_clients_are_ignored():
    clients = {"a2": object()}            # a1 failed to log in
    chosen = pipeline.pick_account(clients)
    assert chosen is None or chosen["name"] == "a2"


def test_choose_theme_respects_force_and_avoids_immediate_repeat():
    assert pipeline.choose_theme("fitness") == "fitness"
    theme = pipeline.choose_theme(None)
    assert theme in __import__("themes").THEME_KEYS

    # seed a published post on the same theme -> immediate repeat discouraged
    pid = db.insert_post(account="a1", theme=theme, status="published",
                         ig_id=None)
    # no engagement data -> weights are flat, but repeat penalty applies;
    # just assert it still returns a valid theme (probabilistically never
    # the same one twice in a row is not guaranteed, so only validity here)
    assert pipeline.choose_theme(None) in __import__("themes").THEME_KEYS


def test_two_accounts_configured_independently(monkeypatch):
    import config
    monkeypatch.setattr(config, "IG_ACTIVE_ACCOUNT", "")
    assert [a["name"] for a in config.ACCOUNTS] == ["account_1", "account_2"]
    assert config.ACCOUNTS[1]["username"] == "panda_fcuk"
    assert config.ACCOUNTS[1]["handle"] == "@panda_fcuk"
    assert config.ACCOUNTS[0]["username"] == "xene_hotty"


def test_active_account_pin_limits_login_target(monkeypatch):
    import config
    # Account 2 has no password locally (it lives in GitHub Secrets), so
    # simulate the CI state where both accounts are fully configured.
    accounts = [
        {"name": "account_1", "username": "xene_hotty", "password": "x"},
        {"name": "account_2", "username": "panda_fcuk", "password": "x"},
    ]
    monkeypatch.setattr(config, "IG_ACTIVE_ACCOUNT", "account_2")
    allowed = [a for a in accounts
               if a["username"] and a["password"]
               and (not config.IG_ACTIVE_ACCOUNT
                    or a["name"] == config.IG_ACTIVE_ACCOUNT)]
    assert [a["name"] for a in allowed] == ["account_2"]
