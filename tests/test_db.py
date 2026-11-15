"""Tests for the SQLite state layer (temporary DB, no network)."""

import pytest

import db
from datetime import datetime, timedelta


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "engine.db")
    yield


def test_post_lifecycle():
    pid = db.insert_post(account="a1", theme="night_neon", title="line",
                         status="building")
    db.update_post(pid, status="publishing")
    p = db.get_post(pid)
    assert p["status"] == "publishing"
    db.update_post(pid, status="published",
                   published_at=datetime.now().isoformat(timespec="seconds"))
    assert db.get_post(pid)["status"] == "published"


def test_daily_cap_counting():
    pid = db.insert_post(account="a1", status="published",
                         published_at=datetime.now().isoformat(timespec="seconds"))
    assert db.count_published_today("a1") == 1
    assert db.count_published_today("other") == 0
    # older post does not count
    db.insert_post(account="a1", status="published",
                   published_at=(datetime.now() - timedelta(days=1))
                   .isoformat(timespec="seconds"))
    assert db.count_published_today("a1") == 1


def test_last_published_and_gap():
    assert db.last_published_at() is None
    assert db.minutes_since_last_publish() == float("inf")
    db.insert_post(account="a1", status="published",
                   published_at=datetime.now().isoformat(timespec="seconds"))
    assert db.minutes_since_last_publish() < 5


def test_stale_publishing():
    db.insert_post(account="a1", status="publishing")
    stale = db.stale_publishing(min_age_minutes=0)
    assert len(stale) == 1
    assert db.stale_publishing(min_age_minutes=9999) == []


def test_pick_asset_prefers_unused_then_lru():
    cands = ["a", "b", "c"]
    assert db.pick_asset("track", cands) == "a"       # never used
    db.mark_asset("track", "a")
    assert db.pick_asset("track", cands) == "b"       # b now never used
    db.mark_asset("track", "b")
    db.mark_asset("track", "c")
    # all used -> oldest used_at wins
    assert db.pick_asset("track", cands) == "a"
    assert db.is_asset_used("track", "a")
    assert db.pick_asset("track", []) is None


def test_line_uniqueness():
    assert db.insert_line("t", "Some unique line here friend", "norm1",
                          engine="llm") is True
    assert db.insert_line("t", "Some unique line here friend", "norm1",
                          engine="llm") is False
    assert db.line_exists("norm1")
    fresh = db.available_generated("t")
    assert len(fresh) == 1
    db.mark_line_used("norm1")
    assert db.available_generated("t") == []
    assert db.line_count() == 1


def test_theme_performance_medians():
    p1 = db.insert_post(account="a", theme="fitness", status="published",
                        ig_id="m1")
    p2 = db.insert_post(account="a", theme="fitness", status="published",
                        ig_id="m2")
    p3 = db.insert_post(account="a", theme="beach_golden", status="published",
                        ig_id="m3")
    db.upsert_insight("m1", "a", likes=10, comments=0, post_id=p1)
    db.upsert_insight("m2", "a", likes=30, comments=0, post_id=p2)
    db.upsert_insight("m3", "a", likes=5, comments=5, post_id=p3)
    perf = db.theme_performance()
    assert perf["fitness"] == 20          # median of 10, 30
    assert perf["beach_golden"] == 10


def test_state_kv_roundtrip():
    assert db.get_state("k", "d") == "d"
    db.set_state("k", "v")
    assert db.get_state("k") == "v"
    db.set_state("k", "v2")
    assert db.get_state("k") == "v2"


def test_runs():
    rid = db.start_run("test-slot")
    db.finish_run(rid, "published", post_id=1, error=None)
    conn = db.connect()
    row = conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
    conn.close()
    assert row["status"] == "published"
    assert row["slot"] == "test-slot"
