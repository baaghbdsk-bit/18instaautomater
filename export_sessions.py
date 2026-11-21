"""
export_sessions.py — turn local instagrapi sessions into GitHub Secret values.

The GitHub runner cannot solve an Instagram challenge, so it needs a session
that was already authenticated here. This script base64-encodes the local
session files and writes them to a single text file **outside the repo**.

It never prints the session contents: anyone holding them can take over the
account. Open the generated file yourself, copy one line at a time into
GitHub -> Settings -> Secrets and variables -> Actions.

Usage:
    python export_sessions.py                # all local sessions
    python export_sessions.py --user xene_hotty
"""

import argparse
import base64
import sys
from pathlib import Path

from config import ACCOUNTS, SESSIONS_DIR

DEFAULT_OUT = Path.home() / "ig-session-secrets.txt"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export sessions as secrets")
    parser.add_argument("--user", default=None, help="Only this IG username")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    out = Path(args.out).expanduser()
    lines: list[str] = []
    exported: list[str] = []

    for idx, account in enumerate(ACCOUNTS, start=1):
        username = account.get("username")
        if not username:
            continue
        if args.user and username != args.user:
            continue
        path = SESSIONS_DIR / f"{username}.json"
        if not path.exists():
            print(f"[!] {username}: no session file at {path}")
            continue
        blob = base64.b64encode(path.read_bytes()).decode("ascii")
        lines.append(f"IG_SESSION_{idx}={blob}")
        exported.append(f"IG_SESSION_{idx}  <-  {path.name}  ({len(blob)} chars)")

    if not lines:
        print("[!] Nothing exported. Run a login first (python insta_login.py).")
        return 1

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[+] Wrote {len(lines)} secret value(s) to:\n    {out}")
    for row in exported:
        print(f"    {row}")
    print("\n[!] Treat that file as a password. Do not commit, paste or share it.")
    print("    Delete it after adding the secrets to GitHub.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
