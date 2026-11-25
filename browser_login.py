"""
browser_login.py — Interactive browser login for Instagram.

Opens a visible browser window. You log in normally (handles 2FA, challenges,
prompts, etc.). As soon as you are logged in, this script captures your session
cookies, converts them for the instagrapi pipeline, saves sessions/<username>.json,
and generates the base64 secret for GitHub Actions.
"""

import base64
import sys
import time
from pathlib import Path
from instagrapi import Client
from playwright.sync_api import sync_playwright

from config import SESSIONS_DIR

DEFAULT_SECRET_OUT = Path.home() / "ig-session-secrets.txt"


def main():
    print("=" * 65)
    print("  INSTAGRAM BROWSER LOGIN HELPER")
    print("=" * 65)
    print("Opening a browser window...")
    print("Please log in to your Instagram account (@xene_hotty) in the browser.")
    print("If asked to 'Save your login info', click 'Save Info' or 'Not Now'.")
    print("Waiting for login to complete (timeout: 5 minutes)...\n")

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # Launch real Chromium window
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ]
        )
        context = browser.new_context(
            viewport=None,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        page.goto("https://www.instagram.com/accounts/login/")

        sessionid = None
        ds_user_id = None
        start_time = time.time()
        timeout = 300  # 5 minutes

        while time.time() - start_time < timeout:
            cookies = context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in cookies}
            if "sessionid" in cookie_dict and "ds_user_id" in cookie_dict:
                # Confirm we are past the login page
                current_url = page.url
                if "/accounts/login" not in current_url:
                    sessionid = cookie_dict["sessionid"]
                    ds_user_id = cookie_dict["ds_user_id"]
                    print("[+] Detected login cookies!")
                    time.sleep(3)  # wait for any remaining cookies/redirects
                    break
            time.sleep(1)

        browser.close()

    if not sessionid:
        print("[!] Timed out or login was not completed. Exiting.")
        return 1

    print("\n[*] Initializing instagrapi session with captured cookies...")
    cl = Client()
    cl.delay_range = [1, 3]

    try:
        cl.login_by_sessionid(sessionid)
        info = cl.account_info()
        username = getattr(info, "username", None) or "xene_hotty"
        print(f"[+] Verified active session as @{username} (ID: {cl.user_id})")

        session_path = SESSIONS_DIR / f"{username}.json"
        cl.dump_settings(session_path)
        print(f"[+] Saved valid session to {session_path}")

        # Also generate the base64 secret for GitHub Actions
        blob = base64.b64encode(session_path.read_bytes()).decode("ascii")
        out_file = Path.home() / f"ig-session-secret-{username}.txt"
        out_file.write_text(f"IG_SESSION_1={blob}\n", encoding="utf-8")
        
        print("\n" + "=" * 65)
        print("  LOGIN SUCCESSFUL!")
        print("=" * 65)
        print(f"[+] Exported secret for GitHub Actions saved to:")
        print(f"    {out_file}")
        print("\nNext step:")
        print(f"1. Open {out_file.name} in your user folder.")
        print("2. Copy the value and paste it into GitHub -> Settings -> Secrets -> IG_SESSION_1.")
        print("=" * 65)
        return 0

    except Exception as e:
        print(f"[!] Failed to convert session for instagrapi: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
