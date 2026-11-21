"""
music_match.py — pick Instagram catalog audio that fits the scene's mood.

The old picker chose a random track from the global trending list, which is why
sad, sultry or cinematic posts were getting random generic songs. Each curated
scene variation carries a mood (e.g. "playful and alluring"); we turn that into
one or two targeted catalog searches, then rank the results by how well their
title/artist matches the search terms. If no mood match is available we fall
back to the global trending list, so music never blocks a publish.
"""

# Curated mood -> catalog search queries. Keep queries short: Instagram's
# global audio search works best with 1-3 word phrases.
MOOD_QUERIES = {
    "intimate": ("intimate r&b", "slow sensual"),
    "calm": ("chill lofi", "soft acoustic"),
    "relaxed": ("chill acoustic", "easy listening"),
    "introspective": ("lofi chill", "melancholy piano"),
    "bold": ("confident hip hop", "power anthem"),
    "electric": ("energetic dance", "electronic beat"),
    "high fashion": ("fashion runway", "luxury house"),
    "commanding": ("powerful cinematic", "dramatic beat"),
    "dreamy": ("dreamy pop", "romantic chill"),
    "free": ("summer chill", "carefree pop"),
    "luxurious": ("luxury lounge", "smooth r&b"),
    "carefree": ("upbeat summer", "happy pop"),
    "ambitious": ("motivational", "confident pop"),
    "playful": ("playful pop", "flirty"),
    "alluring": ("slow r&b", "sensual"),
    "vibrant": ("upbeat dance", "festival"),
    "dramatic": ("cinematic dramatic", "epic orchestral"),
    "urban": ("urban hip hop", "street rap"),
    "wistful": ("melancholy", "sad piano"),
}


def mood_queries(mood: str | None) -> list[str]:
    """Return all distinct catalog search queries for a scene mood.

    The first query that returns results is used for the catalog search; all
    of them are used for scoring, so a mixed mood like "playful and alluring"
    does not let a generic pop track beat an actual slow/sensual one.
    """
    text = (mood or "").lower()
    found: list[str] = []
    for key, queries in MOOD_QUERIES.items():
        if key in text:
            found.extend(queries)
    out: list[str] = []
    for query in found:
        if query not in out:
            out.append(query)
    return out


def score_track(track, queries: list[str]) -> float:
    """Higher when the track's title/artist echoes the mood query terms."""
    if not queries:
        return 0.0
    title = str(getattr(track, "title", "") or "")
    artist = str(getattr(track, "display_artist", "") or "")
    text = f"{title} {artist}".lower()
    score = 0.0
    for query in queries:
        for term in query.lower().replace("&", "").split():
            if len(term) >= 3 and term in text:
                score += 1.0
    return score


def track_key(track) -> str:
    return str(getattr(track, "id", "") or
               getattr(track, "audio_asset_id", "") or "")
