"""
local_music.py — local music bank for Reels (custom tier first, then CC-BY).

Modelled on the working reel-engine design: no Instagram catalog API is
required. Tracks are shipped under assets/music/custom/ (owner-supplied) or
assets/music/{chill,dark,energy}/ (CC-BY 4.0, credited in CREDITS.json). They
are muxed into the MP4 by generate_video.still_video(), so playback is audible
on every platform. Rotation is stored in SQLite and never repeats a track
until the whole pool has been used.
"""

import json
import time
from pathlib import Path

import db
from config import MUSIC_CREDIT, MUSIC_DIR

AUDIO_EXTS = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac")
CUSTOM_DIR = MUSIC_DIR / "custom"


def all_tracks(custom_only: bool = False) -> list[Path]:
    roots = [CUSTOM_DIR] if custom_only else [CUSTOM_DIR, MUSIC_DIR]
    found: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                found.setdefault(str(p), p)
    return sorted(found.values(), key=str)


def credits() -> dict:
    path = MUSIC_DIR / "CREDITS.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def clean_name(path: Path) -> str:
    """Filename -> credit name (e.g. 'bye (slowed).mp3' -> 'bye slowed')."""
    stem = path.stem
    for char in "()[]{}":
        stem = stem.replace(char, " ")
    for char in "_-":
        stem = stem.replace(char, " ")
    return " ".join(stem.split())


def credit_for(track: Path) -> str:
    """Custom tracks use their filename; CC-BY tracks use CREDITS.json."""
    if CUSTOM_DIR in track.parents:
        return f"Music: {clean_name(track)}"
    for key, info in credits().items():
        if Path(key).name == track.name and isinstance(info, dict):
            return str(info.get("credit") or MUSIC_CREDIT)
    return MUSIC_CREDIT


def _state_key(track: Path) -> str:
    return f"music:local:{track.parent.name}:{track.name}"


def _last_used(track: Path) -> float:
    raw = db.get_state(_state_key(track))
    try:
        return float(raw) if raw else 0.0
    except ValueError:
        return 0.0


def pick_local_track(custom_only: bool = False) -> dict | None:
    """Pick a custom track (if any) or a least-recently-used stock track.

    ``custom_only=True`` is used by the pipeline to check for owner-supplied
    audio before trying the curated catalog bank.
    """
    custom = all_tracks(custom_only=True)
    pool = custom if custom_only else (custom or all_tracks())
    if not pool:
        return None
    chosen = min(pool, key=_last_used)
    db.set_state(_state_key(chosen), str(time.time()))
    return {
        "path": str(chosen),
        "pool": "custom" if chosen in custom else chosen.parent.name,
        "title": clean_name(chosen),
        "credit": credit_for(chosen),
        "source": "local_bank",
    }
