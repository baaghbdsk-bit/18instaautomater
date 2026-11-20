"""
insta_login.py — INTERACTIVE Instagram login + session/cookie saver.

You type the credentials yourself; nothing is hardcoded and nothing is printed
back. The script logs in through instagrapi (session/cookie auth, NOT Graph API),
saves the authenticated session to sessions/<username>.json, and verifies it
with a cheap account_info() call. It NEVER creates a post.

Usage:
    python insta_login.py                 # interactive login
    python insta_login.py --check alice   # inspect a cached session, no network
    python insta_login.py --help

Optional: after a successful login you will be asked whether to also save the
credentials into .env so the automated pipeline can reuse the session later.
.env is gitignored — never commit it.
"""

import argparse
import getpass
import sys
from pathlib import Path

from config import BASE_DIR, SESSIONS_DIR
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, TwoFactorRequired


def _upsert_env(values: dict) -> None:
    """Add or replace KEY=value lines in .env without touching other keys."""
    env_path = BASE_DIR / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    keys = set(values)
    out = []
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else None
        if key in keys:
            out.append(f"{key}={values[key]}")
            keys.discard(key)
        else:
            out.append(line)
    for key in keys:
        out.append(f"{key}={values[key]}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"[+] Credentials written to {env_path.name} (gitignored).")


def _two_factor_code(secret: str | None) -> str | None:
    if secret:
        try:
            import pyotp
            return pyotp.TOTP(secret).now()
        except Exception:  # noqa: BLE001
            print("[!] Could not generate a TOTP code from the supplied secret.")
    try:
        return input("Enter the 2FA code from your authenticator app: ").strip() or None
    except (EOFError, KeyboardInterrupt):
        return None


def _try_login(client: Client, username: str, password: str,
               secret: str | None) -> bool:
    """Attempt login, handling 2FA. Returns True on success."""
    try:
        client.login(username, password)
        return True
    except TwoFactorRequired:
        code = _two_factor_code(secret)
        if not code:
            print("[!] No 2FA code available — login aborted.")
            return False
        client.two_factor_login(code)
        return True
    except ChallengeRequired as e:
        print(f"[!] Instagram raised a security challenge: {str(e)[:200]}")
        print("    Complete it in the Instagram app, delete "
              f"sessions/{username}.json, then run this script again.")
        return False


def interactive_login() -> int:
    print("=== Instagram interactive login (session/cookie based) ===")
    print("Nothing you type is echoed back or logged.\n")
    username = input("Instagram username: ").strip()
    if not username:
        print("[!] Username is required.")
        return 1
    password = getpass.getpass("Instagram password (hidden): ")
    if not password:
        print("[!] Password is required.")
        return 1
    secret = getpass.getpass(
        "2FA secret, base32 (blank if you do not use 2FA): ").strip() or None

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_file = SESSIONS_DIR / f"{username}.json"

    client = Client()
    client.delay_range = [1, 3]

    if session_file.exists():
        print(f"[*] Found cached session: {session_file.name}")
        try:
            client.load_settings(session_file)
            if _try_login(client, username, password, secret):
                print("[+] Existing session restored and verified.")
                client.dump_settings(session_file)
                return _finish(client, username, session_file, password, secret)
            return 1
        except ChallengeRequired as e:
            print(f"[!] Challenge on cached session: {str(e)[:200]}")
            print("    Complete it in the app, delete the session file, re-run.")
            return 1
        except Exception as e:  # noqa: BLE001
            print(f"[-] Cached session unusable ({str(e)[:150]}); trying fresh login.")
            client = Client()
            client.delay_range = [1, 3]

    if not _try_login(client, username, password, secret):
        return 1

    client.dump_settings(session_file)
    print(f"[+] Session + cookies saved to {session_file}")
    return _finish(client, username, session_file, password, secret)


def _finish(client: Client, username: str, session_file: Path,
            password: str, secret: str | None) -> int:
    try:
        info = client.account_info()
        print(f"[+] Verified live session as @{getattr(info, 'username', username)}")
    except Exception as e:  # noqa: BLE001
        print(f"[!] Login succeeded but verification failed: {str(e)[:200]}")
        return 1

    answer = input("\nSave these credentials to .env so the pipeline can reuse "
                   "the session? [y/N]: ").strip().lower()
    if answer == "y":
        values = {
            "IG_USERNAME_1": username,
            "IG_PASSWORD_1": password,
            "IG_2FA_SECRET_1": secret or "",
        }
        _upsert_env(values)
        print("    You can set IG_HANDLE_1 in .env for the image watermark.")
    else:
        print("[i] Credentials not saved. The pipeline also needs them in .env "
              "to reuse this session later.")

    print("\nDone. No post was made. To test publishing later, run:")
    print("  python pipeline.py --dry-run --strict   (no publish)")
    print("  python pipeline.py --strict --slot first-live   (real post, after approval)")
    return 0


def check_session(username: str) -> int:
    path = SESSIONS_DIR / f"{username}.json"
    if not path.exists():
        print(f"[i] No cached session for {username} at {path}")
        return 1
    size = path.stat().st_size
    print(f"[+] Cached session for {username}: {path} ({size} bytes)")
    print("    Contents are intentionally not displayed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", metavar="USERNAME",
                        help="Only inspect a cached session file, no login/network")
    args = parser.parse_args()
    if args.check:
        return check_session(args.check)
    return interactive_login()


if __name__ == "__main__":
    sys.exit(main())
