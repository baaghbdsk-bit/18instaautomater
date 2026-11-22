"""Local music bank: custom tier first, LRU rotation, correct attribution."""

import json
from pathlib import Path

import db
import local_music
from config import MUSIC_DIR


def test_local_bank_has_licensed_tracks():
    tracks = local_music.all_tracks()
    assert len(tracks) >= 15
    assert all(p.suffix.lower() in local_music.AUDIO_EXTS for p in tracks)


def test_credits_resolve_by_filename_despite_stale_paths():
    assert Path(MUSIC_DIR / "CREDITS.json").exists()
    tracks = local_music.all_tracks()
    credited = [local_music.credit_for(p) for p in tracks]
    assert all(c.startswith("Music:") for c in credited)
    assert any("Kevin MacLeod" in c and "CC BY 4.0" in c for c in credited)


def test_custom_track_credit_from_filename():
    fake = MUSIC_DIR / "custom" / "bye (slowed).mp3"
    assert local_music.credit_for(fake) == "Music: bye slowed"


def test_pick_uses_least_recently_used(monkeypatch):
    tracks = local_music.all_tracks()
    assert len(tracks) >= 2
    # Force all but the last track to look recently used.
    now = 2_000_000_000.0
    for p in tracks[:-1]:
        db.set_state(local_music._state_key(p), str(now))
    db.set_state(local_music._state_key(tracks[-1]), "0")

    chosen = local_music.pick_local_track()
    assert chosen["path"] == str(tracks[-1])
    assert chosen["source"] == "local_bank"
    assert chosen["credit"].startswith("Music:")


def test_custom_tier_wins_when_present(monkeypatch):
    custom = MUSIC_DIR / "custom" / "owner-track.mp3"
    other = local_music.all_tracks()[0]

    def fake_all(custom_only=False):
        return [custom] if custom_only else [custom, other]

    monkeypatch.setattr(local_music, "all_tracks", fake_all)
    monkeypatch.setattr(local_music, "_last_used", lambda p: 0.0)
    chosen = local_music.pick_local_track()
    assert chosen["pool"] == "custom"
    assert chosen["credit"] == "Music: owner track"
