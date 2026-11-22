"""
db.py — SQLite state for the reel engine (port of the reference db.js).

Single committed source of truth: posts, generated lines, asset usage,
insights, runs. CI checkpoints the WAL and commits this file back so
duplicate-post protection and rotation survive between runs.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from config import DB_PATH

# Status lifecycle for posts:
#   building -> built -> publishing -> published
#   building -> built -> dry-run
#   any -> failed            (definite failure)
#   publishing -> published|failed   (resolved by crash reconciliation)
STATUSES = ("building", "built", "publishing", "published",
            "partial", "failed", "dry-run", "skipped")

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
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
CREATE TABLE IF NOT EXISTS generated_lines (
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
CREATE TABLE IF NOT EXISTS used_assets (
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    used_at TEXT NOT NULL,
    PRIMARY KEY (kind, key)
);
CREATE TABLE IF NOT EXISTS insights (
    media_id TEXT PRIMARY KEY,
    post_id INTEGER,
    account TEXT,
    likes INTEGER,
    comments INTEGER,
    collected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    slot TEXT,
    status TEXT NOT NULL,
    post_id INTEGER,
    error TEXT
);
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published_at);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.executescript(SCHEMA)
    # Additive vertical schema (static quote-image posts). Idempotent and
    # lazy so importing db.py never pulls in the migration until a DB opens.
    from migrations import migrate as _migrate
    if _migrate(conn):
        conn.commit()
    return conn


def checkpoint() -> None:
    """Fold the WAL into the main file so engine.db is safe to commit."""
    try:
        conn = connect()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except Exception as e:  # noqa: BLE001
        print(f"[db] checkpoint failed: {e}")


# ---------------------------------------------------------------------------
# state kv
# ---------------------------------------------------------------------------
def get_state(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = connect()
    row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_state(key: str, value: str) -> None:
    conn = connect()
    conn.execute("INSERT INTO state(key,value) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------
def start_run(slot: str) -> int:
    conn = connect()
    cur = conn.execute(
        "INSERT INTO runs(started_at, slot, status) VALUES(?,?,?)",
        (_now(), slot, "running"))
    conn.commit()
    run_id = cur.lastrowid
    conn.close()
    return run_id


def finish_run(run_id: int, status: str, post_id: Optional[int] = None,
               error: Optional[str] = None) -> None:
    conn = connect()
    conn.execute(
        "UPDATE runs SET finished_at=?, status=?, post_id=?, error=? WHERE id=?",
        (_now(), status, post_id, (error or "")[:900], run_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# posts
# ---------------------------------------------------------------------------
def insert_post(**fields) -> int:
    fields.setdefault("created_at", _now())
    fields.setdefault("status", "building")
    cols = ",".join(fields)
    marks = ",".join("?" for _ in fields)
    conn = connect()
    cur = conn.execute(f"INSERT INTO posts({cols}) VALUES({marks})",
                       tuple(fields.values()))
    conn.commit()
    post_id = cur.lastrowid
    conn.close()
    return post_id


def update_post(post_id: int, **fields) -> None:
    if not fields:
        return
    sets = ",".join(f"{k}=?" for k in fields)
    conn = connect()
    conn.execute(f"UPDATE posts SET {sets} WHERE id=?", (*fields.values(), post_id))
    conn.commit()
    conn.close()


def get_post(post_id: int) -> Optional[dict]:
    conn = connect()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def recent_posts(limit: int = 20, account: Optional[str] = None) -> List[dict]:
    conn = connect()
    if account:
        rows = conn.execute(
            "SELECT * FROM posts WHERE account=? ORDER BY id DESC LIMIT ?",
            (account, limit)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def stale_publishing(min_age_minutes: int = 0) -> List[dict]:
    """Rows left in 'publishing' — candidates for crash reconciliation."""
    cutoff = (datetime.now() - timedelta(minutes=min_age_minutes)).isoformat(
        timespec="seconds")
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM posts WHERE status IN ('publishing','partial') "
        "AND created_at <= ? ORDER BY id", (cutoff,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _midnight() -> str:
    return datetime.now().replace(hour=0, minute=0, second=0,
                                  microsecond=0).isoformat(timespec="seconds")


def count_published_today(account: str) -> int:
    conn = connect()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM posts WHERE account=? AND status='published' "
        "AND COALESCE(published_at, created_at) >= ?",
        (account, _midnight())).fetchone()
    conn.close()
    return int(row["n"])


def last_published_at(account: Optional[str] = None) -> Optional[str]:
    sql = ("SELECT MAX(COALESCE(published_at, created_at)) AS t "
           "FROM posts WHERE status='published'")
    params: tuple = ()
    if account:
        sql += " AND account=?"
        params = (account,)
    conn = connect()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row["t"] if row and row["t"] else None


def minutes_since_last_publish(account: Optional[str] = None) -> float:
    last = last_published_at(account)
    if not last:
        return float("inf")
    try:
        ts = datetime.fromisoformat(last)
    except ValueError:
        return float("inf")
    return (datetime.now() - ts).total_seconds() / 60.0


# ---------------------------------------------------------------------------
# asset usage (LRU picks — no image/track repeats until the pool turns over)
# ---------------------------------------------------------------------------
def pick_asset(kind: str, candidates: Sequence[str]) -> Optional[str]:
    """First never-used candidate, else least-recently used."""
    if not candidates:
        return None
    conn = connect()
    rows = conn.execute(
        "SELECT key, used_at FROM used_assets WHERE kind=?", (kind,)).fetchall()
    conn.close()
    used = {r["key"]: r["used_at"] for r in rows}
    for c in candidates:                      # prefer never-used, in given order
        if str(c) not in used:
            return str(c)
    return min(candidates, key=lambda c: used.get(str(c), ""))


def mark_asset(kind: str, key: str) -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO used_assets(kind, key, used_at) VALUES(?,?,?) "
        "ON CONFLICT(kind, key) DO UPDATE SET used_at=excluded.used_at",
        (kind, str(key), _now()))
    conn.commit()
    conn.close()


def is_asset_used(kind: str, key: str) -> bool:
    conn = connect()
    row = conn.execute(
        "SELECT 1 FROM used_assets WHERE kind=? AND key=?",
        (kind, str(key))).fetchone()
    conn.close()
    return row is not None


def asset_usage(kind: str) -> List[dict]:
    conn = connect()
    rows = conn.execute(
        "SELECT key, used_at FROM used_assets WHERE kind=? ORDER BY used_at",
        (kind,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def prune_assets(kind: str, keep_last: int = 500) -> None:
    conn = connect()
    rows = conn.execute(
        "SELECT key FROM used_assets WHERE kind=? ORDER BY used_at DESC",
        (kind,)).fetchall()
    if len(rows) > keep_last:
        doomed = [r["key"] for r in rows[keep_last:]]
        conn.executemany(
            "DELETE FROM used_assets WHERE kind=? AND key=?",
            [(kind, k) for k in doomed])
        conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# generated lines
# ---------------------------------------------------------------------------
def line_exists(norm: str) -> bool:
    conn = connect()
    row = conn.execute(
        "SELECT 1 FROM generated_lines WHERE norm=?", (norm,)).fetchone()
    conn.close()
    return row is not None


def insert_line(theme: str, line: str, norm: str, engine: str,
                caption: Optional[str] = None,
                hashtags: Optional[str] = None) -> bool:
    """Returns False when the normalised line already exists."""
    conn = connect()
    cur = conn.execute(
        "INSERT INTO generated_lines(theme, line, norm, caption, hashtags, "
        "engine, created_at) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(norm) DO NOTHING",
        (theme, line, norm, caption, hashtags, engine, _now()))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def mark_line_used(norm: str) -> None:
    conn = connect()
    conn.execute("UPDATE generated_lines SET used_at=? WHERE norm=?",
                 (_now(), norm))
    conn.execute(
        "INSERT INTO used_assets(kind, key, used_at) VALUES('line', ?, ?) "
        "ON CONFLICT(kind, key) DO UPDATE SET used_at=excluded.used_at",
        (norm, _now()))
    conn.commit()
    conn.close()


def available_generated(theme: str, limit: int = 5) -> List[dict]:
    """Unused generated lines for a theme, oldest first."""
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM generated_lines WHERE theme=? AND used_at IS NULL "
        "ORDER BY id LIMIT ?", (theme, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def recent_lines(limit: int = 40) -> List[dict]:
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM generated_lines ORDER BY id DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def line_count() -> int:
    conn = connect()
    n = conn.execute("SELECT COUNT(*) AS n FROM generated_lines").fetchone()["n"]
    conn.close()
    return int(n)


# ---------------------------------------------------------------------------
# insights (engagement proxy for theme weighting)
# ---------------------------------------------------------------------------
def upsert_insight(media_id: str, account: str, likes: int, comments: int,
                   post_id: Optional[int] = None) -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO insights(media_id, post_id, account, likes, comments, "
        "collected_at) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(media_id) DO UPDATE SET likes=excluded.likes, "
        "comments=excluded.comments, collected_at=excluded.collected_at",
        (str(media_id), post_id, account, int(likes or 0), int(comments or 0),
         _now()))
    conn.commit()
    conn.close()


def insight_for(media_id: str) -> Optional[dict]:
    conn = connect()
    row = conn.execute("SELECT * FROM insights WHERE media_id=?",
                       (str(media_id),)).fetchone()
    conn.close()
    return dict(row) if row else None


def theme_performance() -> dict:
    """Median engagement (likes + comments) per theme over published posts."""
    conn = connect()
    rows = conn.execute(
        "SELECT p.theme AS theme, (i.likes + i.comments) AS eng "
        "FROM posts p JOIN insights i ON i.media_id = p.ig_id "
        "WHERE p.status='published' AND p.theme IS NOT NULL "
        "AND p.ig_id IS NOT NULL").fetchall()
    conn.close()
    by_theme: dict = {}
    for r in rows:
        by_theme.setdefault(r["theme"], []).append(int(r["eng"] or 0))
    medians = {}
    for theme, vals in by_theme.items():
        vals.sort()
        n = len(vals)
        medians[theme] = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    return medians


# ---------------------------------------------------------------------------
# migration: legacy posted_history.json (if present)
# ---------------------------------------------------------------------------
def import_legacy_history(path: Path) -> int:
    """One-time import of posted_history.json into the posts table."""
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[db] could not read legacy history: {e}")
        return 0
    conn = connect()
    imported = 0
    for p in data.get("posts", []):
        norm = (p.get("overlay") or "").strip().lower()
        if not norm:
            continue
        row = conn.execute(
            "SELECT 1 FROM posts WHERE title=? AND account=? AND created_at=?",
            (p.get("overlay"), p.get("account"), p.get("ts"))).fetchone()
        if row:
            continue
        conn.execute(
            "INSERT INTO posts(created_at, account, title, caption_text, "
            "video_path, image_path, image_source, status, published_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (p.get("ts") or _now(), p.get("account"), p.get("overlay"),
             p.get("caption"), p.get("video"), p.get("image"),
             p.get("image_source"), "published", p.get("ts") or _now()))
        imported += 1
    conn.commit()
    conn.close()
    if imported:
        path.rename(path.with_suffix(".json.imported"))
        print(f"[db] imported {imported} legacy posts from {path.name}")
    return imported


# ---------------------------------------------------------------------------
# static quote-image vertical (migration 001)
# ---------------------------------------------------------------------------
# Lifecycle stages for the vertical. Kept separate from STATUSES above so the
# legacy reel statuses/queries are untouched.
STAGES = ("pending", "quote_selected", "image_generating", "image_downloaded",
          "composition_complete", "ready_to_publish", "published", "failed",
          "skipped", "dry_run")

_STAGE_FIELDS = ("status", "generation_status", "composition_status")


def claim_quote(quote_id: str, post_id: int) -> bool:
    """Atomically reserve a quote. False means another run already claimed it."""
    conn = connect()
    cur = conn.execute(
        "INSERT INTO quote_usage(quote_id, post_id, used_at) VALUES(?,?,?) "
        "ON CONFLICT(quote_id) DO NOTHING",
        (str(quote_id), post_id, _now()))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def quote_already_used(quote_id: str) -> bool:
    conn = connect()
    row = conn.execute(
        "SELECT 1 FROM quote_usage WHERE quote_id=?", (str(quote_id),)).fetchone()
    conn.close()
    return row is not None


def used_quote_ids() -> set:
    conn = connect()
    rows = conn.execute("SELECT quote_id FROM quote_usage").fetchall()
    conn.close()
    return {r["quote_id"] for r in rows}


def update_post_stage(post_id: int, **fields) -> None:
    """update_post, but stage-bearing fields must hold a valid STAGES value."""
    for key in _STAGE_FIELDS:
        value = fields.get(key)
        if value is not None and value not in STAGES:
            raise ValueError(
                f"invalid {key}: {value!r} (expected one of {STAGES})")
    update_post(post_id, **fields)


def posts_by_stage(stage: str, limit: int = 20) -> List[dict]:
    """Posts currently sitting in a given vertical stage (any stage column)."""
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM posts WHERE status=? OR generation_status=? "
        "OR composition_status=? ORDER BY id DESC LIMIT ?",
        (stage, stage, stage, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def recent_posts_need_recovery() -> List[dict]:
    """In-flight posts older than five minutes — crash recovery candidates."""
    cutoff = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM posts WHERE status IN ('building','built','publishing',"
        "'image_generating','ready_to_publish') "
        "AND created_at <= ? ORDER BY id", (cutoff,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
