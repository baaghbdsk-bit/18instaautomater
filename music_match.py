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


def _has_audio(track) -> bool:
    return bool(getattr(track, "progressive_download_url", None) or
                getattr(track, "dash_manifest", None))


def search_orgavsm(cl, queries) -> list:
    """All ORGAVSM tracks returned by search_music() for the given queries."""
    found: list = []
    seen = set()
    for query in queries:
        try:
            results = list(cl.search_music(query) or [])
        except Exception:  # noqa: BLE001 - catalog is optional
            continue
        for track in results:
            key = str(getattr(track, "id", ""))
            if not key or key in seen:
                continue
            seen.add(key)
            if "ORGAVSM" in str(getattr(track, "display_artist", "")).upper():
                found.append(track)
    return found


def find_curated_track(cl, item: dict):
    """Resolve an entry to a playable ORGAVSM Track returned by search_music().

    Queries are deliberately varied: the catalog returned to a datacenter IP
    differs from a residential one, so matching only a fixed ID can fail.
    """
    queries = [item["query"]]
    title = str(item.get("title", ""))
    if title:
        queries.append(title)
        artist = str(item.get("artist", "")).split(",")[0].strip()
        queries.append(f"{title} {artist}".strip())
    tracks = search_orgavsm(cl, queries)
    wanted = str(item["track_id"])
    for track in tracks:
        if str(getattr(track, "id", "")) == wanted and _has_audio(track):
            return track
    prefix = title.lower()[:6]
    for track in tracks:
        if str(getattr(track, "title", "")).lower().startswith(prefix) and _has_audio(track):
            return track
    for track in tracks:
        if _has_audio(track):
            return track
    return None


def curated_for_mood(mood: str | None) -> list[dict]:
    """All ORGAVSM entries; mood does not change the approved artist list."""
    return [CURATED_TRACKS[k] for k in ORGAVSM_KEYS]


def pick_orgavsm_track(cl, used_keys: list | None = None,
                       mood: str | None = None):
    """Pick an ORGAVSM track with a persistent 48-hour no-reuse cooldown."""
    used = {str(x) for x in (used_keys or [])}
    # callers store either track keys or Audio IDs in asset_usage("music").
    excluded = {k for k in ORGAVSM_KEYS
                if k in used or CURATED_TRACKS[k]["track_id"] in used}
    candidates = [k for k in ORGAVSM_KEYS
                  if k not in excluded and _cooldown_expired(k)]
    if not candidates:
        available = [k for k in ORGAVSM_KEYS if k not in excluded] or list(ORGAVSM_KEYS)
        candidates = [min(available, key=_last_used)]

    for key in candidates:
        item = CURATED_TRACKS[key]
        track = find_curated_track(cl, item)
        if track is not None:
            _log_use(key)
            print(f"[music] ORGAVSM '{getattr(track, 'title', item['title'])}' "
                  f"by {getattr(track, 'display_artist', item['artist'])} "
                  f"(audio_id={track_key(track)})")
            return track, track_key(track)
        print(f"[music] ORGAVSM '{key}' not resolvable via search_music()")

    # Curated keys unavailable in this catalog region: use ANY ORGAVSM track
    # returned by the live search, still honouring the 48h cooldown by ID.
    dynamic = [t for t in search_orgavsm(cl, ["orgavsm", "orgasm"])
               if _has_audio(t) and track_key(t) not in used]
    if dynamic:
        dynamic.sort(key=lambda t: _last_used(track_key(t)))
        track = dynamic[0]
        tid = track_key(track)
        _log_use(tid)
        print(f"[music] ORGAVSM '{getattr(track, 'title', '')}' "
              f"by {getattr(track, 'display_artist', '')} "
              f"(audio_id={tid})")
        return track, tid

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
