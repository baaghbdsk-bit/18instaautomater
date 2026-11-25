"""
post_youtube.py — Upload vertical reels directly to YouTube Shorts via the official YouTube Data API v3.

Authentication:
  - Uses OAuth 2.0 Credentials with offline refresh token.
  - Can read from sessions/youtube_token.json (local) or environment variables:
      YOUTUBE_CLIENT_ID
      YOUTUBE_CLIENT_SECRET
      YOUTUBE_REFRESH_TOKEN
"""

import json
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from config import SESSIONS_DIR

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = SESSIONS_DIR / "youtube_token.json"


def is_configured() -> bool:
    """Return True if YouTube credentials exist either on disk or in environment."""
    if TOKEN_FILE.exists():
        return True
    return bool(
        os.getenv("YOUTUBE_CLIENT_ID")
        and os.getenv("YOUTUBE_CLIENT_SECRET")
        and os.getenv("YOUTUBE_REFRESH_TOKEN")
    )


def get_credentials() -> Optional[Credentials]:
    """Retrieve and refresh YouTube OAuth2 credentials."""
    creds = None

    # 1. Try local token file
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as e:
            print(f"[-] Could not load {TOKEN_FILE}: {e}")

    # 2. Try environment variables (used by GitHub Actions)
    if not creds or not creds.valid:
        client_id = os.getenv("YOUTUBE_CLIENT_ID")
        client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
        refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

        if client_id and client_secret and refresh_token:
            creds = Credentials(
                None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )

    if not creds:
        return None

    # Refresh token if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed credentials back to disk if token file exists
            if TOKEN_FILE.exists():
                TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        except Exception as e:
            print(f"[!] YouTube token refresh failed: {e}")
            return None

    return creds


def get_youtube_service():
    """Build and return an authorized YouTube Data API client."""
    creds = get_credentials()
    if not creds:
        raise RuntimeError("No valid YouTube credentials found. Run setup_youtube.py first.")
    return build("youtube", "v3", credentials=creds)


def upload_short(
    video_path: str | Path,
    title: str,
    description: str = "",
    tags: Optional[list[str]] = None,
    privacy_status: str = "public",
) -> dict:
    """
    Upload an MP4 vertical video to YouTube Shorts.

    Returns:
        {"ok": bool, "id": str | None, "url": str | None, "error": str | None}
    """
    path = Path(video_path)
    if not path.is_file() or path.stat().st_size == 0:
        return {"ok": False, "id": None, "url": None, "error": f"File missing or empty: {video_path}"}

    # Ensure #shorts is in the title and description for YouTube algorithm
    clean_title = title.strip()
    if "#shorts" not in clean_title.lower():
        clean_title = (clean_title[:85].rstrip() + " #shorts").strip()
    else:
        clean_title = clean_title[:100]

    desc = description.strip()
    if "#shorts" not in desc.lower():
        desc = (desc + "\n\n#shorts #trending #viral").strip()

    if tags is None:
        tags = ["shorts", "trending", "viral", "reels"]

    body = {
        "snippet": {
            "title": clean_title,
            "description": desc,
            "tags": tags,
            "categoryId": "22",  # People & Blogs / Entertainment
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    try:
        service = get_youtube_service()
        media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True)
        request = service.videos().insert(part="snippet,status", body=body, media_body=media)

        print(f"[*] Uploading to YouTube Shorts: {clean_title}...")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"    Progress: {int(status.progress() * 100)}%")

        video_id = response.get("id")
        short_url = f"https://youtube.com/shorts/{video_id}"
        print(f"[+] Published to YouTube Shorts: {short_url}")
        return {"ok": True, "id": video_id, "url": short_url, "error": None}

    except HttpError as e:
        err_msg = f"YouTube API error ({e.resp.status}): {e.content.decode('utf-8', errors='replace')}"
        print(f"[!] {err_msg}")
        return {"ok": False, "id": None, "url": None, "error": err_msg}
    except Exception as e:
        print(f"[!] YouTube upload failed: {e}")
        return {"ok": False, "id": None, "url": None, "error": str(e)}
