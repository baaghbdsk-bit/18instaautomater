"""
post_instagram.py — instagrapi publishing with retry and duplicate safety.

WARNING: Instagram's Terms of Service prohibit automation on personal
accounts. Volume is deliberately kept low (see config cadence guards).

Safety model (port of the reference engine's publish/index.js):
  * uploads retry with jittered backoff — but ONLY after confirming the
    caption's first line is not already live on the account, so a retry
    can never double-post;
  * recent_media()/find_duplicate() give the orchestrator a last-12-posts
    caption check before every publish;
  * media_info() feeds the engagement stats used for theme weighting.
"""

import time
from pathlib import Path
from typing import Optional

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    ClientError,
    LoginRequired,
    TwoFactorRequired,
)

from config import SESSIONS_DIR
from net import with_retry

SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(username: str) -> Path:
    return SESSIONS_DIR / f"{username}.json"


def _generate_totp(secret: str) -> str | None:
    if not secret:
        return None
    try:
        import pyotp
        return pyotp.TOTP(secret).now()
    except ImportError:
        print("[!] pyotp not installed; cannot auto-generate 2FA code.")
        print("    Install with: pip install pyotp")
        return None


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------
def login_account(account: dict) -> Client:
    """Log in, reusing a saved session when possible. Retries network errors."""
    username = account["username"]
    password = account["password"]
    secret = account.get("two_factor_secret", "")
    sess_file = _session_path(username)

    def attempt() -> Client:
        cl = Client()
        cl.delay_range = [1, 3]          # human-like pacing between API calls
        if sess_file.exists():
            try:
                cl.load_settings(sess_file)
                cl.login(username, password)
                print(f"[+] {account['name']}: restored session ({username})")
                return cl
            except (ChallengeRequired, TwoFactorRequired):
                raise                     # handled below, not a network issue
            except Exception as e:        # noqa: BLE001 — stale session
                print(f"[-] {account['name']}: session invalid, re-logging ({e})")

        try:
            cl.login(username, password)
        except TwoFactorRequired:
            code = _generate_totp(secret)
            if code is None:
                raise RuntimeError(
                    f"{account['name']}: 2FA required but no pyotp/secret.")
            cl.two_factor_login(code)
            print(f"[+] {account['name']}: logged in with 2FA ({username})")
        except ChallengeRequired as e:
            print(f"[!] {account['name']}: Instagram challenge. Complete it "
                  f"manually in the app, delete the session file and re-run. {e}")
            raise
        except ClientError as e:
            print(f"[-] {account['name']}: login failed -> {e}")
            raise

        try:
            cl.dump_settings(sess_file)
        except Exception as e:  # noqa: BLE001
            print(f"[!] {account['name']}: could not save session: {e}")
        print(f"[+] {account['name']}: logged in ({username})")
        return cl

    # Network flakiness is retried; auth problems are not (retrying burns
    # Instagram's patience on challenges).
    return with_retry(
        attempt, attempts=3, base_ms=2000, label=f"login:{username}",
        is_retryable=lambda e: not isinstance(
            e, (ChallengeRequired, TwoFactorRequired, ClientError, LoginRequired,
                RuntimeError)))


# ---------------------------------------------------------------------------
# media inspection (duplicate check / reconciliation / insights)
# ---------------------------------------------------------------------------
def recent_media(cl: Client, username: str, amount: int = 15) -> list | None:
    """
    Latest media for the account as dicts: pk, code, caption, likes, comments.
    Returns None when the fetch FAILS (vs [] for a genuinely empty account) so
    reconciliation can defer instead of wrongly failing a row.
    """
    try:
        uid = cl.user_id_from_username(username)
        medias = cl.user_medias(uid, amount=amount)
    except Exception as e:  # noqa: BLE001
        print(f"[ig] recent_media failed: {e}")
        return None
    out = []
    for m in medias:
        out.append({
            "pk": str(m.pk),
            "code": getattr(m, "code", "") or "",
            "caption": (getattr(m, "caption_text", "") or ""),
            "likes": int(getattr(m, "like_count", 0) or 0),
            "comments": int(getattr(m, "comment_count", 0) or 0),
            "taken_at": getattr(m, "taken_at", None),
        })
    return out


def first_line(text: str) -> str:
    for ln in (text or "").splitlines():
        if ln.strip():
            return " ".join(ln.strip().lower().split())
    return ""


def find_duplicate(cl: Client, username: str, caption: str,
                   lookback: int = 12) -> Optional[str]:
    """Return the pk of a live post whose first caption line matches, else None."""
    target = first_line(caption)
    if len(target) < 8:
        return None
    for m in recent_media(cl, username, amount=lookback) or []:
        if first_line(m["caption"]) == target:
            return m["pk"]
    return None


def media_info(cl: Client, pk: str) -> Optional[dict]:
    """Engagement stats for one media (used for theme weighting)."""
    try:
        info = cl.media_info(pk)
        return {
            "pk": str(info.pk),
            "likes": int(getattr(info, "like_count", 0) or 0),
            "comments": int(getattr(info, "comment_count", 0) or 0),
        }
    except Exception as e:  # noqa: BLE001
        print(f"[ig] media_info({pk}) failed: {e}")
        return None


def preflight(cl: Client) -> str:
    """Cheap authenticated call; raises if the session is dead."""
    info = cl.account_info()
    return getattr(info, "username", "") or ""


# ---------------------------------------------------------------------------
# uploads
# ---------------------------------------------------------------------------
def upload_reel(cl: Client, username: str, video_path, caption: str,
                attempts: int = 3) -> dict:
    """
    Upload a Reel with safe retry.

    Returns {ok, media, recovered, error}:
      ok=True,  media=Media           -> posted now
      ok=True,  recovered=True        -> a retry attempt found it already live
      ok=False                         -> definite failure (nothing live)
    """
    path = str(video_path)
    last_err = None
    for i in range(attempts):
        try:
            media = cl.clip_upload(path, caption=caption)
            print(f"    [reel] posted {Path(path).name}")
            return {"ok": True, "pk": str(media.pk),
                    "code": getattr(media, "code", "") or "",
                    "recovered": False, "error": None}
        except (ChallengeRequired, LoginRequired) as e:
            return {"ok": False, "pk": None, "code": "", "recovered": False,
                    "error": f"{type(e).__name__}: {e}"}
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"    [!] reel upload attempt {i + 1}/{attempts} failed: {e}")
            if i == attempts - 1:
                break
            # Back off, then CHECK whether the post actually went live before
            # risking a second upload (this is the double-post guard).
            time.sleep(8 * (i + 1))
            dup = find_duplicate(cl, username, caption, lookback=8)
            if dup:
                print("    [+] upload actually succeeded — found it live "
                      f"(pk={dup})")
                return {"ok": True, "pk": dup, "code": "", "recovered": True,
                        "error": None}
    return {"ok": False, "pk": None, "code": "", "recovered": False,
            "error": f"{type(last_err).__name__}: {last_err}"}


def post_reel(cl: Client, video_path, caption: str = "") -> bool:
    """Simple boolean wrapper (legacy main.py API)."""
    return upload_reel(cl, "", video_path, caption, attempts=2)["ok"]


def post_feed(cl: Client, video_path, caption: str = "") -> bool:
    try:
        cl.video_upload(str(video_path), caption=caption)
        print(f"    [feed] posted {video_path}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"    [!] feed upload failed: {e}")
        return False


def post_story(cl: Client, video_path) -> bool:
    try:
        cl.video_upload_to_story(str(video_path))
        print(f"    [story] posted {video_path}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"    [!] story upload failed: {e}")
        return False


def logout_all(clients: dict) -> None:
    for name, cl in clients.items():
        try:
            cl.logout()
            print(f"[-] {name}: logged out")
        except Exception:  # noqa: BLE001
            pass
