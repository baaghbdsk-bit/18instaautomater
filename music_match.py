"""
music_match.py — catalog music for the account, using ORGAVSM Audio IDs only.

Every track is resolved live from Instagram's catalog via search_music(); no
hardcoded Audio ID is ever used as a playable fallback. Tracks rotate with a
48-hour no-reuse cooldown stored in SQLite so it survives CI restarts, and the
resolved Audio ID + use-count are logged on every selection.
"""

import time

import db

# ORGAVSM-only curated entries. track_id is used ONLY to verify a search
# result; the playable track always comes from search_music().
CURATED_TRACKS = {
    "touch_my_body": {"track_id": "1113847643557725",
                      "title": "Touch my body", "artist": "ORGAVSM",
                      "query": "orgavsm"},
    "naughty": {"track_id": "3715502165250716", "title": "Naughty",
                "artist": "ORGAVSM", "query": "orgavsm"},
    "kiss_me_love_me": {"track_id": "4157656211135184",
                        "title": "Kiss Me, Love Me", "artist": "ORGAVSM",
                        "query": "orgavsm"},
    "your_kind_of_love": {"track_id": "1080036577506579",
                          "title": "Your Kind of Love", "artist": "ORGAVSM",
                          "query": "orgavsm"},
    "in_your_fantasy": {"track_id": "4386426898239074",
                        "title": "In Your Fantasy", "artist": "ROSE ORGAVSM",
                        "query": "orgavsm"},
}

ORGAVSM_KEYS = tuple(CURATED_TRACKS)
SLOWBURN_KEYS: tuple = ()
REUSE_COOLDOWN_SECONDS = 48 * 3600


def _last_used(key: str) -> float:
    raw = db.get_state(f"orgavsm_last_used:{key}")
    try:
        return float(raw) if raw else 0.0
    except ValueError:
        return 0.0


def _cooldown_expired(key: str) -> bool:
    return (time.time() - _last_used(key)) > REUSE_COOLDOWN_SECONDS


def _log_use(key: str) -> int:
    try:
        count = int(db.get_state(f"orgavsm_use_count:{key}") or 0) + 1
    except ValueError:
        count = 1
    db.set_state(f"orgavsm_use_count:{key}", str(count))
    db.set_state(f"orgavsm_last_used:{key}", str(time.time()))
    print(f"[music] ORGAVSM '{key}' used (count={count})")
    return count


def find_curated_track(cl, item: dict):
    """Resolve a curated entry to a Track returned by search_music()."""
    try:
        tracks = list(cl.search_music(item["query"]) or [])
    except Exception:  # noqa: BLE001 - catalog is optional
        return None
    wanted = str(item["track_id"])
    for track in tracks:
        if str(getattr(track, "id", "")) == wanted:
            return track
    title = str(item.get("title", "")).lower()[:6]
    for track in tracks:
        if str(getattr(track, "title", "")).lower().startswith(title):
            return track
    return None


def curated_for_mood(mood: str | None) -> list[dict]:
    """All ORGAVSM entries; mood does not change the approved artist list."""
    return [CURATED_TRACKS[k] for k in ORGAVSM_KEYS]


def pick_orgavsm_track(cl, used_keys: list | None = None,
                       mood: str | None = None):
    """Pick an ORGAVSM track with a persistent 48-hour no-reuse cooldown."""
    used = set(used_keys or [])
    candidates = [k for k in ORGAVSM_KEYS
                  if k not in used and _cooldown_expired(k)]
    if not candidates:
        available = [k for k in ORGAVSM_KEYS if k not in used] or list(ORGAVSM_KEYS)
        candidates = [min(available, key=_last_used)]

    for key in candidates:
        item = CURATED_TRACKS[key]
        track = find_curated_track(cl, item)
        if track is not None:
            _log_use(key)
            print(f"[music] ORGAVSM '{item['title']}' by {item['artist']} "
                  f"(audio_id={track_key(track)})")
            return track, track_key(track)
        print(f"[music] ORGAVSM '{key}' not resolvable via search_music()")
    print("[music] no ORGAVSM track available — posting without audio")
    return None, None


def track_from_metadata(cl, music_meta: dict | None):
    """Re-resolve the original post's ORGAVSM track for a cross-post."""
    if not isinstance(music_meta, dict) or not music_meta.get("track_id"):
        return None
    return find_curated_track(
        cl, {"track_id": str(music_meta["track_id"]),
             "title": str(music_meta.get("title", "")), "query": "orgavsm"})


def track_key(track) -> str:
    return str(getattr(track, "id", "") or
               getattr(track, "audio_asset_id", "") or "")
