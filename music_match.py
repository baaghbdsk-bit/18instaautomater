"""
music_match.py — catalog music for the account, using SLOWBURN Audio IDs only.

Every track is resolved live from Instagram's catalog via search_music(); no
hardcoded Audio ID is ever used as a playable fallback. Tracks rotate with a
48-hour no-reuse cooldown stored in SQLite so it survives CI restarts, and the
resolved Audio ID + use-count are logged on every selection.
"""

import time

import db

# SLOWBURN-only curated entries. track_id is used ONLY to verify a search
# result; the playable track always comes from search_music().
CURATED_TRACKS = {
    "possession": {"track_id": "1033349329204662",
                   "title": "POSSESSION", "artist": "SLOWBURN",
                   "query": "slowburn"},
    "make_it_dirty": {"track_id": "4656223218033246",
                      "title": "Make It Dirty", "artist": "SLOWBURN",
                      "query": "slowburn"},
    "make_me_beg": {"track_id": "3288626561313133",
                    "title": "Make Me Beg", "artist": "SLOWBURN",
                    "query": "slowburn"},
    "torture_me_gently": {"track_id": "4393589377523868",
                          "title": "Torture Me Gently", "artist": "SLOWBURN",
                          "query": "slowburn"},
    "dirty_thoughts": {"track_id": "756615490816490",
                       "title": "Dirty Thoughts", "artist": "SLOWBURN",
                       "query": "slowburn"},
    "tease_me": {"track_id": "1469684681247162", "title": "Tease Me",
                 "artist": "SLOWBURN", "query": "slowburn"},
    "crave_you": {"track_id": "876032214956457", "title": "Crave You",
                  "artist": "SLOWBURN", "query": "slowburn"},
    "i_want_you_so_bad": {"track_id": "2321184005071474",
                          "title": "I Want You So Bad", "artist": "SLOWBURN",
                          "query": "slowburn"},
    "naughty_girl": {"track_id": "32503737865937141", "title": "Naughty Girl",
                     "artist": "SLOWBURN", "query": "slowburn r&b"},
    "touch_and_love": {"track_id": "907890151657068", "title": "Touch And Love",
                       "artist": "SLOWBURN", "query": "slowburn r&b"},
}

ORGAVSM_KEYS: tuple = ()
SLOWBURN_KEYS = tuple(CURATED_TRACKS)
REUSE_COOLDOWN_SECONDS = 48 * 3600


def _last_used(key: str) -> float:
    raw = db.get_state(f"music_last_used:{key}")
    try:
        return float(raw) if raw else 0.0
    except ValueError:
        return 0.0


def _cooldown_expired(key: str) -> bool:
    return (time.time() - _last_used(key)) > REUSE_COOLDOWN_SECONDS


def _log_use(key: str) -> int:
    try:
        count = int(db.get_state(f"music_use_count:{key}") or 0) + 1
    except ValueError:
        count = 1
    db.set_state(f"music_use_count:{key}", str(count))
    db.set_state(f"music_last_used:{key}", str(time.time()))
    print(f"[music] SLOWBURN '{key}' used (count={count})")
    return count


def _has_audio(track) -> bool:
    return bool(getattr(track, "progressive_download_url", None) or
                getattr(track, "dash_manifest", None))


def search_slowburn(cl, queries) -> list:
    """All SLOWBURN tracks returned by search_music() for the given queries."""
    found: list = []
    seen = set()
    for query in queries:
        try:
            results = list(cl.search_music(query) or [])
        except Exception as e:  # noqa: BLE001 - catalog can be region-limited
            print(f"[music] search_music({query!r}) failed: "
                  f"{type(e).__name__}: {str(e)[:120]}")
            continue
        for track in results:
            key = str(getattr(track, "id", ""))
            if not key or key in seen:
                continue
            seen.add(key)
            if "SLOWBURN" in str(getattr(track, "display_artist", "")).upper():
                found.append(track)
    return found


def find_curated_track(cl, item: dict, exclude_ids=None):
    """Resolve an entry to a playable SLOWBURN Track from search_music()."""
    exclude = {str(x) for x in (exclude_ids or [])}
    queries = [item["query"], "slowburn", "slow burn"]
    title = str(item.get("title", ""))
    if title:
        queries += [title, f"{title} SLOWBURN"]
    tracks = [t for t in search_slowburn(cl, queries)
              if str(getattr(t, "id", "")) not in exclude]
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
    """All SLOWBURN entries; mood does not change the approved artist list."""
    return [CURATED_TRACKS[k] for k in SLOWBURN_KEYS]


def pick_orgavsm_track(cl, used_keys: list | None = None,
                       mood: str | None = None):
    """Pick a SLOWBURN track with a persistent 48-hour no-reuse cooldown.

    Name kept for call-site compatibility; the approved artist is SLOWBURN.
    """
    used = {str(x) for x in (used_keys or [])}
    excluded = {k for k in SLOWBURN_KEYS
                if k in used or CURATED_TRACKS[k]["track_id"] in used}
    candidates = [k for k in SLOWBURN_KEYS
                  if k not in excluded and _cooldown_expired(k)]
    if not candidates:
        available = [k for k in SLOWBURN_KEYS if k not in excluded] or list(SLOWBURN_KEYS)
        candidates = [min(available, key=_last_used)]

    for key in candidates:
        item = CURATED_TRACKS[key]
        track = find_curated_track(cl, item, exclude_ids=used)
        if track is not None:
            _log_use(key)
            print(f"[music] SLOWBURN '{getattr(track, 'title', item['title'])}' "
                  f"by {getattr(track, 'display_artist', 'SLOWBURN')} "
                  f"(audio_id={track_key(track)})")
            return track, track_key(track)
        print(f"[music] SLOWBURN '{key}' not resolvable via search_music()")

    dynamic = [t for t in search_slowburn(cl, ["slowburn", "slow burn"])
               if _has_audio(t) and track_key(t) not in used]
    if dynamic:
        dynamic.sort(key=lambda t: _last_used(track_key(t)))
        track = dynamic[0]
        tid = track_key(track)
        _log_use(tid)
        print(f"[music] SLOWBURN '{getattr(track, 'title', '')}' "
              f"(audio_id={tid})")
        return track, tid

    print("[music] no SLOWBURN track available — posting without audio")
    return None, None


def track_from_metadata(cl, music_meta: dict | None):
    """Re-resolve the original post's SLOWBURN track for a cross-post."""
    if not isinstance(music_meta, dict) or not music_meta.get("track_id"):
        return None
    return find_curated_track(
        cl, {"track_id": str(music_meta["track_id"]),
             "title": str(music_meta.get("title", "")), "query": "slowburn"})


def track_key(track) -> str:
    return str(getattr(track, "id", "") or
               getattr(track, "audio_asset_id", "") or "")
