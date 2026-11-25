"""
setup_youtube.py — Interactive helper to authorize your YouTube channel.

How it works:
  1. Reads client_secrets.json (from Google Cloud Console)
  2. Opens your browser to authorize your YouTube channel
  3. Saves credentials to sessions/youtube_token.json
  4. Displays YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN
     ready to paste into .env and GitHub Repository Secrets.
"""

import json
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import BASE_DIR, SESSIONS_DIR
from post_youtube import SCOPES, TOKEN_FILE

DEFAULT_CLIENT_SECRETS = BASE_DIR / "client_secrets.json"


def main():
    print("=" * 65)
    print("  YOUTUBE SHORTS INTEGRATION SETUP")
    print("=" * 65)

    secrets_file = DEFAULT_CLIENT_SECRETS
    if not secrets_file.exists():
        print("[!] client_secrets.json not found in the workspace directory.")
        print("\nQuick 3-minute setup instructions:")
        print("1. Go to Google Cloud Console: https://console.cloud.google.com/")
        print("2. Create a project (or select an existing one).")
        print("3. In 'APIs & Services' -> 'Library', search for and enable 'YouTube Data API v3'.")
        print("4. In 'APIs & Services' -> 'OAuth consent screen', choose 'External', enter an App Name and your email, and save.")
        print("5. In 'APIs & Services' -> 'Credentials', click '+ CREATE CREDENTIALS' -> 'OAuth client ID'.")
        print("   - Application type: Desktop app")
        print("   - Name: YouTube Shorts Automator")
        print("6. Download the JSON file, rename it to 'client_secrets.json' and place it in:")
        print(f"   {BASE_DIR / 'client_secrets.json'}")
        print("\nOnce placed, run this script again: python setup_youtube.py")
        return 1

    print(f"[*] Found client secrets at: {secrets_file}")
    print("[*] Launching browser to authorize your YouTube channel...")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), SCOPES)
        creds = flow.run_local_server(port=0)

        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        print(f"[+] Saved authorization token to: {TOKEN_FILE}")

        # Test channel info
        service = build("youtube", "v3", credentials=creds)
        resp = service.channels().list(part="snippet", mine=True).execute()
        items = resp.get("items", [])
        if items:
            ch_title = items[0]["snippet"]["title"]
            print(f"[+] Connected Channel: {ch_title}")

        # Extract secrets for GitHub Actions & .env
        with open(secrets_file, "r", encoding="utf-8") as f:
            sec_data = json.load(f)
        client_info = sec_data.get("installed") or sec_data.get("web") or {}
        client_id = client_info.get("client_id", "")
        client_secret = client_info.get("client_secret", "")
        refresh_token = creds.refresh_token or ""

        out_path = Path.home() / "youtube-secrets.txt"
        secret_content = (
            f"YOUTUBE_CLIENT_ID={client_id}\n"
            f"YOUTUBE_CLIENT_SECRET={client_secret}\n"
            f"YOUTUBE_REFRESH_TOKEN={refresh_token}\n"
        )
        out_path.write_text(secret_content, encoding="utf-8")

        print("\n" + "=" * 65)
        print("  YOUTUBE AUTHORIZATION SUCCESSFUL!")
        print("=" * 65)
        print(f"Values have been saved to: {out_path}")
        print("\nAdd these 3 keys to GitHub Repo -> Settings -> Secrets -> Actions:")
        print(f"  1. YOUTUBE_CLIENT_ID")
        print(f"  2. YOUTUBE_CLIENT_SECRET")
        print(f"  3. YOUTUBE_REFRESH_TOKEN")
        print("=" * 65)
        return 0

    except Exception as e:
        print(f"[!] Setup failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
