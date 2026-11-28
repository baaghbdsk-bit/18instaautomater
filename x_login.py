"""
x_login.py — Interactive X (Twitter) login & storage_state exporter for GitHub Actions.

Matches NeuBench-Automator's anti-detect browser setup (real Chrome channel when
available, ``--disable-blink-features=AutomationControlled``, no ``--enable-automation``,
and persistent context) so Google OAuth / X login never triggers "This browser or app
may not be secure".

Saves full Playwright ``storage_state`` (cookies + localStorage) to
``x_session/cookies.json`` and writes base64 to ``x_session/x_cookies_b64.txt``
(plus copies it to your Windows clipboard) for GitHub Secret ``X_COOKIES_BASE64``.

Usage:
    python x_login.py
"""

import base64
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
X_SESSION_DIR = ROOT / "x_session"
PROFILE_DIR = X_SESSION_DIR / "browser_profile"
COOKIES_PATH = X_SESSION_DIR / "cookies.json"
B64_PATH = X_SESSION_DIR / "x_cookies_b64.txt"


def _copy_to_clipboard(text: str) -> bool:
    try:
        subprocess.run(["clip"], input=text, text=True, check=True)
        return True
    except Exception:
        return False


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[!] playwright is not installed. Run: pip install playwright && playwright install chromium")
        return 1

    X_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("X-Post-Automater: 1-Time Session Setup")
    print("=" * 60)
    print("A real browser window is about to open.")
    print("1. Log in to your X (Twitter) account (Google or username/password).")
    print("2. Complete any 2FA or verification if prompted.")
    print("3. Wait until you see your normal X Home Feed.")
    print("4. Return here or wait — auto-detecting login (up to 5 min)...")
    print("=" * 60 + "\n")

    launch_kwargs = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "viewport": {"width": 1280, "height": 850},
        "ignore_default_args": ["--enable-automation"],
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--start-maximized",
        ],
    }

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
        except Exception:
            context = p.chromium.launch_persistent_context(**launch_kwargs)

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://x.com/login", timeout=60000)

        deadline = time.time() + 300
        logged_in = False
        while time.time() < deadline:
            cookies = context.cookies()
            names = {
                c.get("name")
                for c in cookies
                if "x.com" in c.get("domain", "") or "twitter.com" in c.get("domain", "")
            }
            if "auth_token" in names and "ct0" in names:
                page.wait_for_timeout(2500)
                logged_in = True
                break
            time.sleep(1.5)

        if not logged_in:
            print("[!] Timed out waiting for X login.")
            context.close()
            return 1

        # Save full storage_state (cookies + localStorage), matching NeuBench-Automator
        context.storage_state(path=str(COOKIES_PATH))
        b64 = base64.b64encode(COOKIES_PATH.read_bytes()).decode("ascii")
        B64_PATH.write_text(b64, encoding="utf-8")
        copied = _copy_to_clipboard(b64)
        context.close()

    print(f"\n[+] Saved full X storage_state -> {COOKIES_PATH}")
    print(f"[+] Saved base64 string -> {B64_PATH}")
    if copied:
        print("[+] Copied X_COOKIES_BASE64 to your clipboard! Paste it into GitHub Secrets.")
    else:
        print(f"[*] Copy the contents of {B64_PATH} into GitHub Secret: X_COOKIES_BASE64")
    return 0


if __name__ == "__main__":
    sys.exit(main())
