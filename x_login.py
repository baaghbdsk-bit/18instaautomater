"""
x_login.py — Interactive X (Twitter) login & cookie exporter for GitHub Actions.

Opens a visible Chromium window to https://x.com/i/flow/login, waits until
you complete login (including 2FA if enabled), saves ``x_session/cookies.json``,
and writes the base64 string to ``x_session/x_cookies_b64.txt`` (also copied
to the Windows clipboard when available) for your ``X_COOKIES_BASE64`` secret.

Usage:
    python x_login.py
"""

import base64
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
X_SESSION_DIR = ROOT / "x_session"
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
    print("[*] Launching Chromium for X login...")
    print("[*] Please log in to your X account in the browser window.")
    print("[*] Waiting up to 5 minutes for auth_token + ct0 cookies...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width": 1280, "height": 850})
        page = ctx.new_page()
        page.goto("https://x.com/i/flow/login", timeout=60000)

        deadline = time.time() + 300
        logged_in = False
        while time.time() < deadline:
            cookies = ctx.cookies()
            names = {c.get("name") for c in cookies if "x.com" in c.get("domain", "") or "twitter.com" in c.get("domain", "")}
            if "auth_token" in names and "ct0" in names:
                # Give X a moment to finish settling session storage
                page.wait_for_timeout(2000)
                cookies = ctx.cookies()
                logged_in = True
                break
            time.sleep(1.5)

        if not logged_in:
            print("[!] Timed out waiting for X login.")
            browser.close()
            return 1

        COOKIES_PATH.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
        b64 = base64.b64encode(COOKIES_PATH.read_bytes()).decode("ascii")
        B64_PATH.write_text(b64, encoding="utf-8")
        copied = _copy_to_clipboard(b64)
        browser.close()

    print(f"\n[+] Saved {len(cookies)} cookies -> {COOKIES_PATH}")
    print(f"[+] Saved base64 string -> {B64_PATH}")
    if copied:
        print("[+] Copied X_COOKIES_BASE64 to your clipboard! Paste it into GitHub Secrets.")
    else:
        print(f"[*] Copy the contents of {B64_PATH} into GitHub Secret: X_COOKIES_BASE64")
    return 0


if __name__ == "__main__":
    sys.exit(main())
