"""
curated_audio.py — hand-picked real songs resolved by Instagram Audio ID.

The catalog search endpoint is unreliable from CI, but ``track_info_by_id``
returns fresh metadata (including a playable audio URL) for known IDs. IDs and
titles were verified live; the 48-hour LRU rotation lives in SQLite. The audio
is downloaded and muxed into the Reel by generate_video.still_video().
"""

import re
import subprocess
import time
from pathlib import Path

import db
from config import FFMPEG_BIN, TMP_DIR

# (Audio ID, title, artist) — actual songs, not stock production music.
CURATED = (
    ("1358099786319553", "Dracula", "Tame Impala"),
    ("201971177433133", "After Hours", "The Weeknd"),
    ("731507439939389", "Sao Paulo", "The Weeknd, Anitta"),
    ("4207179866261956", "Apocalypse", "Cigarettes After Sex"),
    ("464992933372678", "Timeless", "The Weeknd, Playboi Carti"),
    ("609632436429286", "Blinding Lights", "The Weeknd"),
    ("562335654115610", "The Less I Know The Better", "Tame Impala"),
    ("876032214956457", "Crave You", "SLOWBURN"),
    ("1033349329204662", "POSSESSION", "SLOWBURN"),
    ("4656223218033246", "Make It Dirty", "SLOWBURN"),
    ("3288626561313133", "Make Me Beg", "SLOWBURN"),
    ("4393589377523868", "Torture Me Gently", "SLOWBURN"),
    ("756615490816490", "Dirty Thoughts", "SLOWBURN"),
    ("1469684681247162", "Tease Me", "SLOWBURN"),
    ("2321184005071474", "I Want You So Bad", "SLOWBURN"),
    ("32503737865937141", "Naughty Girl", "SLOWBURN"),
    ("907890151657068", "Touch And Love", "SLOWBURN"),
)
CACHE_DIR = TMP_DIR / "audio_cache"


def _last_used(track_id: str) -> float:
    raw = db.get_state(f"music:curated:{track_id}")
    try:
        return float(raw) if raw else 0.0
    except ValueError:
        return 0.0


def _music_asset(cl, track_id: str) -> dict | None:
    try:
        data = cl.track_info_by_id(track_id) or {}
    except Exception as e:  # noqa: BLE001 - dead ID degrades to next pick
        print(f"[curated] {track_id} lookup failed: {type(e).__name__}")
        return None
    return (((data.get("metadata") or {}).get("music_info") or {})
            .get("music_asset_info") or None)


def _audio_url(info: dict) -> str | None:
    manifest = info.get("dash_manifest") or ""
    match = re.search(r"<BaseURL>(.*?)</BaseURL>", manifest, re.DOTALL)
    if not match:
        return None
    return match.group(1).replace("&amp;", "&")


def _download(track_id: str, url: str, start: float = 0.0) -> Path | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"{track_id}.m4a"
    if out.exists() and out.stat().st_size > 20000:
        return out
    cmd = [FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{start:.1f}", "-i", url, "-t", "60",
           "-vn", "-c:a", "aac", "-b:a", "160k", str(out)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except OSError:
        return None
    if proc.returncode != 0 or not out.exists() or out.stat().st_size < 20000:
        print(f"[curated] download failed {track_id}: {proc.stderr[-200:]}")
        return None
    return out


def pick_curated_track(cl) -> dict | None:
    """Resolve and download the least-recently-used curated song."""
    now = time.time()
    ordered = sorted(CURATED, key=lambda item: _last_used(item[0]))
    for track_id, title, artist in ordered:
        info = _music_asset(cl, track_id)
        if not info:
            continue
        url = _audio_url(info)
        if not url:
            continue
        highlights = info.get("highlight_start_times_in_ms") or []
        start = (float(highlights[0]) / 1000.0) if highlights else 0.0
        path = _download(track_id, url, start)
        if path is None:
            continue
        db.set_state(f"music:curated:{track_id}", str(now))
        return {
            "path": str(path),
            "pool": "curated",
            "title": info.get("title") or title,
            "artist": info.get("display_artist") or artist,
            "track_id": track_id,
            "audio_cluster_id": info.get("audio_cluster_id") or "",
            "credit": f"Music: {info.get('title') or title} — "
                      f"{info.get('display_artist') or artist}",
            "source": "curated_catalog",
        }
    return None
