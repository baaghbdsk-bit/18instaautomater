"""
bootstrap_sessions.py — materialize cached Instagram sessions inside CI.

Why this exists
---------------
A GitHub runner starts with an empty ``sessions/`` directory and a datacenter
IP. A cold password login from that IP almost always raises an Instagram
challenge, which cannot be solved unattended — that is why every cloud run
failed before this file existed.

The fix is to ship a session that was already authenticated on the machine
that created it. The session JSON is stored as an encrypted GitHub Secret
(base64), never in the repo and never in the logs.

Secrets (both optional):
    IG_SESSION_1  ->  sessions/<IG_USERNAME_1>.json
    IG_SESSION_2  ->  sessions/<IG_USERNAME_2>.json

Rules:
  * an existing session file from the Actions cache always wins, so a session
    refreshed by a previous run is not downgraded to an older snapshot;
  * a missing/invalid secret is skipped, never fatal;
  * secret contents are never printed.

Generate the secret value locally with ``python export_sessions.py``.
"""

import base64
import binascii
import json
import os
import stat
import sys

from config import ACCOUNTS, SESSIONS_DIR

# Session files that instagrapi can actually restore.
REQUIRED_KEYS = ("authorization_data", "uuids", "cookies")


def _decode(raw: str) -> dict:
    """Accept base64 (preferred) or raw JSON. Raise ValueError on junk."""
    raw = raw.strip()
    if not raw:
        raise ValueError("empty")
    candidates = []
    try:
        candidates.append(base64.b64decode(raw, validate=True).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError):
        pass
    candidates.append(raw)          # tolerate a raw JSON paste
    for text in candidates:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise ValueError("not base64-encoded JSON")


def _write(path, data: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data)
    path.write_text(payload, encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)   # 0600
    except OSError:
        pass
    return len(payload)


def main() -> int:
    written = 0
    for idx, account in enumerate(ACCOUNTS, start=1):
        raw = os.getenv(f"IG_SESSION_{idx}", "")
        username = account.get("username") or os.getenv(f"IG_USERNAME_{idx}", "")
        if not raw:
            continue
        if not username:
            print(f"[-] IG_SESSION_{idx} set but no username configured — skipped")
            continue

        target = SESSIONS_DIR / f"{username}.json"
        if target.exists():
            print(f"[=] {username}: cached session present — keeping it")
            continue

        try:
            data = _decode(raw)
        except ValueError as e:
            print(f"[!] {username}: IG_SESSION_{idx} is unusable ({e}) — skipped")
            continue

        missing = [k for k in REQUIRED_KEYS if k not in data]
        if missing:
            print(f"[!] {username}: IG_SESSION_{idx} missing {missing} — skipped")
            continue

        size = _write(target, data)
        written += 1
        print(f"[+] {username}: seeded session from IG_SESSION_{idx} ({size} bytes)")

    if written == 0:
        print("[=] No sessions seeded (cache and/or secrets absent).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
