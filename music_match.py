"""
music_match.py — catalog music for the account, using SLOWBURN only.

The account owner chose SLOWBURN as the primary music identity for every post,
with ORGAVSM as the only approved secondary rotation. Every track below was
resolved live from Instagram's catalog.

No generic keyword search and no global-trending fallback: if a curated track
cannot be resolved, the post goes out without music rather than with a track
that does not fit the account.
"""

# Verified live in Instagram's catalog (IDs + titles + display artists).
CURATED_TRACKS = {
    "possession": {
        "track_id": "1033349329204662", "title": "POSSESSION",
        "artist": "SLOWBURN", "query": "slowburn",
    },
    "make_it_dirty": {
        "track_id": "4656223218033246", "title": "Make It Dirty",
        "artist": "SLOWBURN", "query": "slowburn",
    },
    "make_me_beg": {
        "track_id": "3288626561313133", "title": "Make Me Beg",
        "artist": "SLOWBURN", "query": "slowburn",
    },
    "torture_me_gently": {
        "track_id": "4393589377523868", "title": "Torture Me Gently",
        "artist": "SLOWBURN", "query": "slowburn",
    },
    "dirty_thoughts": {
        "track_id": "756615490816490", "title": "Dirty Thoughts",
        "artist": "SLOWBURN", "query": "slowburn",
    },
    "tease_me": {
        "track_id": "1469684681247162", "title": "Tease Me",
        "artist": "SLOWBURN", "query": "slowburn",
    },
    "crave_you": {
        "track_id": "876032214956457", "title": "Crave You",
        "artist": "SLOWBURN", "query": "slowburn",
    },
    "i_want_you_so_bad": {
        "track_id": "2321184005071474", "title": "I Want You So Bad",
        "artist": "SLOWBURN", "query": "slowburn",
    },
    "naughty_girl": {
        "track_id": "32503737865937141", "title": "Naughty Girl",
        "artist": "SLOWBURN", "query": "slowburn r&b",
    },
    "touch_and_love": {
        "track_id": "907890151657068", "title": "Touch And Love",
        "artist": "SLOWBURN", "query": "slowburn r&b",
    },
    # Approved secondary rotation (owner: "use orgavsm music").
    "touch_my_body": {
        "track_id": "1113847643557725", "title": "Touch my body",
        "artist": "ORGAVSM", "query": "orgavsm",
    },
    "naughty": {
        "track_id": "3715502165250716", "title": "Naughty",
        "artist": "ORGAVSM", "query": "orgavsm",
    },
    "kiss_me_love_me": {
        "track_id": "4157656211135184", "title": "Kiss Me, Love Me",
        "artist": "ORGAVSM", "query": "orgavsm",
    },
    "your_kind_of_love": {
        "track_id": "1080036577506579", "title": "Your Kind of Love",
        "artist": "ORGAVSM", "query": "orgavsm",
    },
    "in_your_fantasy": {
        "track_id": "4386426898239074", "title": "In Your Fantasy",
        "artist": "ROSE ORGAVSM", "query": "orgavsm",
    },
}

APPROVED_ARTISTS = ("SLOWBURN", "ORGAVSM", "ROSE ORGAVSM")
SLOWBURN_KEYS = tuple(
    key for key, item in CURATED_TRACKS.items()
    if item["artist"] == "SLOWBURN"
)
ORGAVSM_KEYS = tuple(
    key for key, item in CURATED_TRACKS.items()
    if item["artist"] != "SLOWBURN"
)

# Every scene mood maps to SLOWBURN tracks only.
MOOD_TRACKS = {
    "alluring": ("crave_you", "possession", "tease_me", "torture_me_gently"),
    "flirty": ("tease_me", "crave_you", "naughty_girl", "dirty_thoughts"),
    "playful": ("tease_me", "naughty_girl", "i_want_you_so_bad"),
    "bold": ("possession", "make_it_dirty", "make_me_beg", "crave_you"),
    "electric": ("possession", "make_it_dirty", "naughty_girl"),
    "urban": ("make_it_dirty", "possession", "make_me_beg"),
    "commanding": ("possession", "make_me_beg", "torture_me_gently"),
    "high fashion": ("possession", "torture_me_gently", "crave_you"),
    "dreamy": ("touch_and_love", "crave_you", "torture_me_gently"),
    "intimate": ("touch_and_love", "crave_you", "torture_me_gently"),
    "romantic": ("touch_and_love", "i_want_you_so_bad", "crave_you"),
    "calm": ("touch_and_love", "crave_you"),
    "relaxed": ("touch_and_love", "crave_you"),
    "wistful": ("touch_and_love", "torture_me_gently"),
    "introspective": ("touch_and_love", "dirty_thoughts"),
    "dramatic": ("possession", "torture_me_gently", "make_me_beg"),
    "luxurious": ("possession", "crave_you", "touch_and_love"),
    "free": ("i_want_you_so_bad", "naughty_girl"),
    "carefree": ("i_want_you_so_bad", "tease_me"),
    "vibrant": ("naughty_girl", "make_it_dirty"),
    "ambitious": ("possession", "make_me_beg"),
    "default": ("crave_you", "possession", "touch_and_love"),
}

ALL_TRACK_IDS = tuple(item["track_id"] for item in CURATED_TRACKS.values())


def curated_for_mood(mood: str | None) -> list[dict]:
    """Return SLOWBURN entries ordered by relevance to the scene mood."""
    text = (mood or "").lower()
    keys: list[str] = []
    for mood_key, track_keys in MOOD_TRACKS.items():
        if mood_key in text:
            keys.extend(track_keys)
    if not keys:
        keys = list(MOOD_TRACKS["default"])
    out: list[dict] = []
    seen = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        out.append(CURATED_TRACKS[key])
    # Fill with the remaining SLOWBURN tracks first, then ORGAVSM rotation.
    for key in SLOWBURN_KEYS + ORGAVSM_KEYS:
        if key not in seen:
            out.append(CURATED_TRACKS[key])
            seen.add(key)
    return out


def find_curated_track(cl, item: dict):
    """Resolve a curated entry to an instagrapi Track via the live catalog."""
    try:
        tracks = list(cl.search_music(item["query"]) or [])
    except Exception:  # noqa: BLE001 - catalog is optional
        return None
    wanted = str(item["track_id"])
    for track in tracks:
        if str(getattr(track, "id", "")) == wanted:
            return track
    return None


def track_from_metadata(cl, music_meta: dict | None):
    """Re-resolve the exact track used by the original post (for cross-posts)."""
    if not isinstance(music_meta, dict) or not music_meta.get("track_id"):
        return None
    artist = str(music_meta.get("artist", "")).lower()
    query = "orgavsm" if "orgavsm" in artist else "slowburn"
    item = {
        "track_id": str(music_meta["track_id"]),
        "title": str(music_meta.get("title", "")),
        "query": query,
    }
    return find_curated_track(cl, item)


def track_key(track) -> str:
    return str(getattr(track, "id", "") or
               getattr(track, "audio_asset_id", "") or "")
