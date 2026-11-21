"""Tests for session bootstrapping (CI cannot solve Instagram challenges)."""

import base64
import json

import pytest

import bootstrap_sessions


def _session() -> dict:
    return {
        "authorization_data": {"sessionid": "x"},
        "uuids": {"phone_id": "p", "uuid": "u"},
        "cookies": {"csrftoken": "c"},
    }


def test_decode_accepts_base64():
    raw = base64.b64encode(json.dumps(_session()).encode()).decode()
    assert bootstrap_sessions._decode(raw)["cookies"] == {"csrftoken": "c"}


def test_decode_accepts_raw_json():
    assert bootstrap_sessions._decode(json.dumps(_session()))["uuids"]


def test_decode_rejects_junk():
    with pytest.raises(ValueError):
        bootstrap_sessions._decode("not-a-session")


def test_decode_rejects_empty():
    with pytest.raises(ValueError):
        bootstrap_sessions._decode("   ")


def test_write_creates_parent_and_file(tmp_path):
    target = tmp_path / "nested" / "user.json"
    size = bootstrap_sessions._write(target, _session())
    assert target.exists()
    assert size == len(json.dumps(_session()))
    assert json.loads(target.read_text(encoding="utf-8"))["uuids"]


def test_main_seeds_only_missing_sessions(tmp_path, monkeypatch):
    # Two accounts, both with secrets; one already cached.
    accounts = [
        {"name": "account_1", "username": "u1"},
        {"name": "account_2", "username": "u2"},
    ]
    monkeypatch.setattr(bootstrap_sessions, "ACCOUNTS", accounts)
    monkeypatch.setattr(bootstrap_sessions, "SESSIONS_DIR", tmp_path)

    existing = tmp_path / "u1.json"
    existing.write_text(json.dumps({"cached": True}), encoding="utf-8")

    blob = base64.b64encode(json.dumps(_session()).encode()).decode()
    monkeypatch.setenv("IG_SESSION_1", blob)
    monkeypatch.setenv("IG_SESSION_2", blob)

    assert bootstrap_sessions.main() == 0

    # Cached session untouched, missing one seeded.
    assert json.loads(existing.read_text(encoding="utf-8")) == {"cached": True}
    seeded = json.loads((tmp_path / "u2.json").read_text(encoding="utf-8"))
    assert seeded["authorization_data"] == {"sessionid": "x"}


def test_main_skips_unusable_secret(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        bootstrap_sessions, "ACCOUNTS", [{"name": "a", "username": "u"}])
    monkeypatch.setattr(bootstrap_sessions, "SESSIONS_DIR", tmp_path)
    monkeypatch.setenv("IG_SESSION_1", "garbage")

    assert bootstrap_sessions.main() == 0
    assert not (tmp_path / "u.json").exists()
    assert "unusable" in capsys.readouterr().out
