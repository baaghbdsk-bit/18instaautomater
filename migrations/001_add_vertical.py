"""Migration 001 — extend posts for the static quote-image vertical.

Strictly additive: columns are only added when missing, quote_usage is created
only when absent, and the schema version is recorded in state. There is no
UPDATE/DELETE/DROP of existing rows or columns, so legacy posts and generated
lines survive untouched. Running this more than once is a no-op.
"""

import sqlite3

VERSION = 1

# (column name, SQLite column definition) — order is the add order.
NEW_COLUMNS = (
    ("output_kind", "TEXT DEFAULT 'image'"),
    ("quote_id", "TEXT"),
    ("quote_text", "TEXT"),
    ("prompt_text", "TEXT"),
    ("prompt_metadata", "TEXT"),   # JSON string
    ("generation_status", "TEXT"),
    ("generation_path", "TEXT"),
    ("final_image_path", "TEXT"),
    ("composition_status", "TEXT"),
    ("provider", "TEXT"),
    ("model", "TEXT"),
    ("seed", "TEXT"),
    ("attempts", "INTEGER DEFAULT 0"),
    ("error_stage", "TEXT"),
)


def current_version(conn) -> int:
    """Read state['schema_version']; 0 when it has never been set."""
    row = conn.execute(
        "SELECT value FROM state WHERE key=?", ("schema_version",)).fetchone()
    if not row:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def migrate(conn) -> bool:
    """Bring conn up to VERSION. Return True when something was changed.

    Caller owns the commit (db.connect() commits when this returns True).
    """
    changed = False

    have = {row[1] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
    for name, decl in NEW_COLUMNS:
        if name in have:
            continue
        try:
            conn.execute(f"ALTER TABLE posts ADD COLUMN {name} {decl}")
        except sqlite3.OperationalError as exc:
            # A concurrent connection may have added the column between the
            # PRAGMA check and the ALTER. Anything else is a real problem.
            if "duplicate column name" not in str(exc).lower():
                raise
            continue
        changed = True

    has_usage = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_usage'"
    ).fetchone() is not None
    if not has_usage:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS quote_usage ("
            "quote_id TEXT PRIMARY KEY, post_id INTEGER, used_at TEXT NOT NULL)")
        changed = True

    if current_version(conn) != VERSION:
        conn.execute(
            "INSERT INTO state(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(VERSION),))
        changed = True

    return changed
