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

from config import (
    IG_PROXY,
    MUSIC_LIMIT,
    MUSIC_SEARCH_QUERY,
    MUSIC_SOURCE,
    MUSIC_TRENDING_PRODUCT,
    SESSIONS_DIR,
)
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
        if IG_PROXY:
            cl.set_proxy(IG_PROXY)       # stable egress IP for cloud runs
        if sess_file.exists():
            try:
                cl.load_settings(sess_file)
                cl.login(username, password)
                print(f"[+] {account['name']}: restored session ({username})")
                # Refresh the cache so the next run starts from a newer session
                # instead of replaying this one until it expires.
                try:
                    cl.dump_settings(sess_file)
                except Exception:        # noqa: BLE001 - cache is best-effort
                    pass
                return cl
            except TwoFactorRequired:
                raise                     # handled below, not a network issue
            except ChallengeRequired as e:
                # A cached session can be challenged too. A fresh login is the
                # only remaining chance, so fall through instead of giving up.
                print(f"[-] {account['name']}: cached session challenged, "
                      f"trying a fresh login ({e})")
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


def logout_all(clients: dict, invalidate: bool = False) -> None:
    """Release clients without invalidating the saved session by default.

    ``cl.logout()`` tells Instagram to kill the server-side session; calling it
    after a successful post makes the cached sessions/<username>.json unusable
    and forces a fresh login on every run. Keep sessions reusable unless the
    caller explicitly asks to invalidate them.
    """
    for name, cl in clients.items():
        if invalidate:
            try:
                cl.logout()
                print(f"[-] {name}: logged out (session invalidated)")
            except Exception:  # noqa: BLE001
                pass
        else:
            print(f"[-] {name}: session kept for reuse (not invalidated)")
    clients.clear()


# ---------------------------------------------------------------------------
# static image quote posts / session helpers
# ---------------------------------------------------------------------------
def _session_username_hint(cl) -> str:
    """Best-effort username for an error message; never inspects a session file."""
    try:
        name = getattr(cl, "username", "")
        if isinstance(name, str) and name:
            return name
    except Exception:  # noqa: BLE001
        pass
    return "<username>"


def ensure_session(cl) -> str:
    """
    Cheap authenticated call that verifies the cached session is still alive.

    Returns the account username. A dead session is reported with an
    actionable message pointing at the session file to delete — session
    contents (cookies/tokens) are NEVER logged or included in the error.
    """
    try:
        info = cl.account_info()
    except LoginRequired:
        name = _session_username_hint(cl)
        raise RuntimeError(
            f"Instagram session expired — delete sessions/{name}.json "
            "and re-login") from None
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            f"Instagram session check failed ({type(e).__name__}): {e}") from e
    return getattr(info, "username", "") or ""


def upload_photo_post(cl, username: str, image_path, caption: str,
                      attempts: int = 3, track=None) -> dict:
    """
    Publish a static image quote post with safe retry, returning
    {ok, pk, code, recovered, error, attempts}.

    Before every attempt the cached session is verified and the image is
    confirmed present and non-empty. Auth/challenge failures fail fast;
    network failures back off and — crucially — check whether the post
    actually went live before retrying, so a retry can never double-post.
    """
    path = str(image_path)
    image_file = Path(path)
    last_err = None
    attempts_made = 0

    for i in range(attempts):
        # A dead session is a definite failure: never retry into a challenge.
        try:
            ensure_session(cl)
        except Exception as e:  # noqa: BLE001 — includes wrapped LoginRequired
            return {"ok": False, "pk": None, "code": "", "recovered": False,
                    "error": f"session check failed: {type(e).__name__}: {e}",
                    "attempts": attempts_made}

        if not image_file.is_file() or image_file.stat().st_size == 0:
            return {"ok": False, "pk": None, "code": "", "recovered": False,
                    "error": f"image file missing or empty: {path}",
                    "attempts": attempts_made}

        attempts_made += 1
        try:
            if track is not None:
                media = cl.photo_upload_with_music(path, caption=caption,
                                                   track=track)
                label = (getattr(track, "title", None)
                         or (track.get("title") if isinstance(track, dict) else None)
                         or "catalog track")
                print(f"    [photo] posted {image_file.name} with music: {label}")
            else:
                media = cl.photo_upload(path, caption=caption)
                print(f"    [photo] posted {image_file.name} (no music)")
            return {"ok": True, "pk": str(media.pk),
                    "code": getattr(media, "code", "") or "",
                    "recovered": False, "error": None,
                    "attempts": attempts_made}
        except (ChallengeRequired, LoginRequired) as e:
            # Auth/challenge problems burn Instagram's patience — stop now.
            return {"ok": False, "pk": None, "code": "", "recovered": False,
                    "error": f"{type(e).__name__}: {e}",
                    "attempts": attempts_made}
        except Exception as e:  # noqa: BLE001 — network-like failure
            last_err = e
            print(f"    [!] photo upload attempt {i + 1}/{attempts} failed: {e}")
            if i == attempts - 1:
                break
            # Back off, then confirm the caption is not already live before
            # risking a second upload (double-post guard).
            time.sleep(8 * (i + 1))
            dup = find_duplicate(cl, username, caption, lookback=10)
            if dup:
                print("    [+] upload actually succeeded — found it live "
                      f"(pk={dup})")
                return {"ok": True, "pk": dup, "code": "", "recovered": True,
                        "error": None, "attempts": attempts_made}

    error = (f"{type(last_err).__name__}: {last_err}" if last_err
             else "unknown upload error")
    return {"ok": False, "pk": None, "code": "", "recovered": False,
            "error": error, "attempts": attempts_made}


def upload_reel_with_music(cl, username: str, video_path, caption: str,
                           track=None, attempts: int = 3,
                           thumbnail=None) -> dict:
    """Upload a Reel with a catalog track, with the same double-post guard."""
    path = str(video_path)
    video_file = Path(path)
    last_err = None
    made = 0
    for i in range(attempts):
        try:
            ensure_session(cl)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "pk": None, "code": "", "recovered": False,
                    "error": f"session check failed: {type(e).__name__}: {e}",
                    "attempts": made}
        if not video_file.is_file() or video_file.stat().st_size == 0:
            return {"ok": False, "pk": None, "code": "", "recovered": False,
                    "error": f"video file missing or empty: {path}",
                    "attempts": made}
        made += 1
        try:
            if track is not None:
                kwargs = {"caption": caption, "track": track}
                if thumbnail:
                    kwargs["thumbnail"] = str(thumbnail)
                media = cl.clip_upload_with_music(path, **kwargs)
                print(f"    [reel] posted {video_file.name} with music: "
                      f"{getattr(track, 'title', 'catalog track')}")
            else:
                media = cl.clip_upload(path, caption=caption)
                print(f"    [reel] posted {video_file.name} (no music)")
            return {"ok": True, "pk": str(media.pk),
                    "code": getattr(media, "code", "") or "",
                    "recovered": False, "error": None, "attempts": made}
        except (ChallengeRequired, LoginRequired) as e:
            return {"ok": False, "pk": None, "code": "", "recovered": False,
                    "error": f"{type(e).__name__}: {e}", "attempts": made}
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"    [!] reel upload attempt {i + 1}/{attempts} failed: {e}")
            if i == attempts - 1:
                break
            time.sleep(8 * (i + 1))
            dup = find_duplicate(cl, username, caption, lookback=10)
            if dup:
                print(f"    [+] upload actually succeeded — found live (pk={dup})")
                return {"ok": True, "pk": dup, "code": "", "recovered": True,
                        "error": None, "attempts": made}
    error = (f"{type(last_err).__name__}: {last_err}" if last_err
             else "unknown reel upload error")
    return {"ok": False, "pk": None, "code": "", "recovered": False,
            "error": error, "attempts": made}


def _tracks_from_response(data: dict) -> list:
    """Parse Track objects from instagrapi's raw music-browser responses."""
    from instagrapi.extractors import extract_track

    containers: list = []
    for key in ("items", "tracks", "results", "data"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            containers.append(value)
        elif isinstance(value, dict):
            for nested in ("items", "tracks"):
                if isinstance(value.get(nested), list):
                    containers.append(value[nested])
    tracks = []
    for container in containers:
        for item in container:
            raw = item.get("track", item) if isinstance(item, dict) else None
            if not isinstance(raw, dict) or "dash_manifest" not in raw:
                continue  # extract_track needs dash_manifest to build a Track
            try:
                tracks.append(extract_track(dict(raw)))
            except Exception:  # noqa: BLE001 — skip malformed catalog entries
                continue
    return tracks


def find_trending_tracks(cl, source: str | None = None, limit: int | None = None) -> list:
    """Return Instagram catalog Tracks suitable for a photo post.

    source: 'trending' (default) uses music/top_trends + music/trending;
            'search' uses MUSIC_SEARCH_QUERY via music/audio_global_search.
    Never posts, never modifies state. Returns [] when unavailable.
    """
    source = (source or MUSIC_SOURCE).lower()
    limit = int(limit or MUSIC_LIMIT)
    try:
        if source == "search":
            tracks = cl.search_music(MUSIC_SEARCH_QUERY)
            return list(tracks or [])[:limit]
        if source == "off":
            return []
        data = cl.music_top_trends(product=MUSIC_TRENDING_PRODUCT)
        tracks = _tracks_from_response(data)
        if not tracks:
            data = cl.music_trending(product="feed_post")
            tracks = _tracks_from_response(data)
        return tracks[:limit]
    except Exception as e:  # noqa: BLE001 — music is optional, fail soft
        print(f"[music] track discovery failed: {type(e).__name__}: {str(e)[:200]}")
        return []


def pick_music_track(cl, used_keys: list | None = None):
    """Pick a trending catalog track, preferring ones not used recently."""
    tracks = find_trending_tracks(cl)
    if not tracks:
        return None, None
    keys = [str(getattr(t, "id", "") or getattr(t, "audio_asset_id", ""))
            for t in tracks]
    if used_keys:
        unused = [t for t, k in zip(tracks, keys) if k not in set(used_keys)]
        if unused:
            tracks = unused
    import random
    track = random.choice(tracks)
    return track, str(getattr(track, "id", "") or getattr(track, "audio_asset_id", ""))


def session_status(account) -> dict:
    """
    Read-only status of sessions/<username>.json.

    Only the path and byte size are inspected — file contents are never
    opened, read or printed.
    """
    username = account.get("username", "") or ""
    path = _session_path(username)
    size = 0
    if path.is_file():
        try:
            size = path.stat().st_size
        except OSError:  # noqa: BLE001 — raced deletion / permission
            size = 0
    return {"username": username, "cached": size > 0,
            "path": str(path), "size": size}


def preflight_or_login(account, clients: dict) -> Client:
    """Return the cached client for an account, logging in only when missing."""
    name = account["name"]
    if name in clients:
        return clients[name]
    cl = login_account(account)
    clients[name] = cl
    return cl
