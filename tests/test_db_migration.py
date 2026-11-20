"""Migration 001 — legacy rows must survive, new schema must be idempotent."""

import sqlite3
from datetime import datetime, timedelta

import pytest

import db
from migrations import VERSION, current_version, migrate

# The exact pre-migration schema (copied from the old db.SCHEMA).
LEGACY_SCHEMA = """
CREATE TABLE posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    account TEXT,
    theme TEXT,
    title TEXT,
    caption_text TEXT,
    video_path TEXT,
    image_path TEXT,
    image_source TEXT,
    music_path TEXT,
    variant TEXT,
    engine TEXT,
    duration_sec REAL,
    status TEXT NOT NULL,
    ig_id TEXT,
    permalink TEXT,
    error TEXT,
    published_at TEXT
);
CREATE TABLE generated_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    theme TEXT NOT NULL,
    line TEXT NOT NULL,
    norm TEXT NOT NULL UNIQUE,
    caption TEXT,
    hashtags TEXT,
    engine TEXT,
    created_at TEXT NOT NULL,
    used_at TEXT
);
CREATE TABLE used_assets (
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    used_at TEXT NOT NULL,
    PRIMARY KEY (kind, key)
);
CREATE TABLE insights (
    media_id TEXT PRIMARY KEY,
    post_id INTEGER,
    account TEXT,
    likes INTEGER,
    comments INTEGER,
    collected_at TEXT NOT NULL
);
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    slot TEXT,
    status TEXT NOT NULL,
    post_id INTEGER,
    error TEXT
);
CREATE TABLE state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

NEW_COLUMNS = (
    "output_kind", "quote_id", "quote_text", "prompt_text", "prompt_metadata",
    "generation_status", "generation_path", "final_image_path",
    "composition_status", "provider", "model", "seed", "attempts",
    "error_stage",
)


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    path = tmp_path / "engine.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO posts(created_at, account, theme, title, caption_text, "
        "video_path, status) VALUES(?,?,?,?,?,?,?)",
        ("2025-01-02T03:04:05", "acct", "night_neon", "Legacy title",
         "Legacy caption", "assets/video.mp4", "published"))
    conn.execute(
        "INSERT INTO generated_lines(theme, line, norm, caption, hashtags, "
        "engine, created_at) VALUES(?,?,?,?,?,?,?)",
        ("night_neon", "A legacy line", "a-legacy-line", "legacy caption",
         "#tag", "llm", "2025-01-02T03:04:05"))
    conn.commit()
    conn.close()
    return path


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_legacy_db_migrated_without_data_loss(legacy_db):
    conn = db.connect()   # this is where the migration runs
    cols = _columns(conn, "posts")
    for name in NEW_COLUMNS:
        assert name in cols, name

    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_usage'"
    ).fetchone() is not None
    assert current_version(conn) == VERSION

    # Old data is still there, with its values intact.
    post = conn.execute("SELECT * FROM posts WHERE id=1").fetchone()
    assert post["title"] == "Legacy title"
    assert post["caption_text"] == "Legacy caption"
    assert post["video_path"] == "assets/video.mp4"
    assert post["status"] == "published"
    assert post["created_at"] == "2025-01-02T03:04:05"
    line = conn.execute("SELECT * FROM generated_lines WHERE id=1").fetchone()
    assert line["line"] == "A legacy line"
    assert line["norm"] == "a-legacy-line"
    assert line["theme"] == "night_neon"
    assert db.line_count() == 1
    conn.close()

    assert db.get_state("schema_version") == "1"


def test_migration_is_idempotent(legacy_db):
    conn = db.connect()
    assert migrate(conn) is False
    assert migrate(conn) is False
    assert current_version(conn) == VERSION
    assert len(db.recent_posts()) == 1
    assert db.line_count() == 1
    conn.close()


def test_quote_claim_and_stage_validation(legacy_db):
    assert db.claim_quote("quote-1", 1) is True
    assert db.claim_quote("quote-1", 2) is False   # atomic no-repeat guard
    assert db.quote_already_used("quote-1") is True
    assert db.quote_already_used("quote-2") is False
    assert db.used_quote_ids() == {"quote-1"}

    db.update_post_stage(1, generation_status="image_generating")
    assert db.get_post(1)["generation_status"] == "image_generating"
    assert len(db.posts_by_stage("image_generating")) == 1
    assert db.posts_by_stage("does_not_exist") == []

    with pytest.raises(ValueError):
        db.update_post_stage(1, generation_status="not_a_stage")
    with pytest.raises(ValueError):
        db.update_post_stage(1, status="bogus")


def test_fresh_db_gets_migration(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "fresh.db")
    assert db.line_count() == 0
    conn = db.connect()
    for name in NEW_COLUMNS:
        assert name in _columns(conn, "posts"), name
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_usage'"
    ).fetchone() is not None
    assert current_version(conn) == VERSION
    assert migrate(conn) is False
    conn.close()

    pid = db.insert_post(status="building", created_at="2020-01-01T00:00:00")
    assert len(db.recent_posts_need_recovery()) == 1
    db.update_post_stage(pid, status="published")
    assert db.recent_posts_need_recovery() == []

    old = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    fresh = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    db.insert_post(status="publishing", created_at=old)
    db.insert_post(status="publishing", created_at=fresh)
    assert len(db.recent_posts_need_recovery()) == 1
