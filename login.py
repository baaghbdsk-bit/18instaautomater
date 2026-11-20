"""
login.py — authenticate Instagram accounts and cache sessions.

This script does NOT post anything. It only:
  1. reads credentials from .env (via config.ACCOUNTS)
  2. logs in through instagrapi, reusing an existing cached session
  3. verifies the session with a cheap account_info() call
  4. leaves sessions/<username>.json on disk for the pipeline to reuse

It never prints passwords, 2FA secrets, cookies or session-file contents.

Usage:
    python login.py            # log in every configured account
    python login.py --check    # show only cached-session metadata (no network)
"""

import argparse
import sys

from config import ACCOUNTS
from post_instagram import login_account, preflight, session_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Instagram session login helper")
    parser.add_argument("--check", action="store_true",
                        help="Only show cached-session metadata, no login, no network")
    args = parser.parse_args()

    configured = [a for a in ACCOUNTS if a.get("username") and a.get("password")]
    if not configured:
        print("[!] No Instagram credentials configured.")
        print("    Fill IG_USERNAME_1 / IG_PASSWORD_1 (and optionally "
              "IG_2FA_SECRET_1) in .env, then re-run.")
        return 1

    if args.check:
        for acc in configured:
            info = session_status(acc)
            print(f"{acc['name']}: cached={info['cached']} size={info['size']} "
                  f"path={info['path']}")
        return 0

    failures = 0
    for acc in configured:
        print(f"[*] Logging in {acc['name']} ({acc['username']})...")
        try:
            cl = login_account(acc)
            verified = preflight(cl)
            print(f"[+] {acc['name']}: session verified as "
                  f"@{verified or acc['username']} — cached for the pipeline")
            # Intentionally no logout(): keep the freshly saved session usable.
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"[!] {acc['name']}: login failed: {str(e)[:300]}")
            print("    If Instagram raised a challenge, complete it in the app, "
                  "delete sessions/<username>.json, then re-run.")

    print(f"\nDone. {len(configured) - failures}/{len(configured)} account(s) ready.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
