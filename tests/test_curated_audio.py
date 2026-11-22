"""Curated real-song bank resolved by Audio ID, with LRU rotation."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import curated_audio
import db


def test_curated_bank_has_real_songs():
    ids = [item[0] for item in curated_audio.CURATED]
    assert len(ids) >= 15
    assert len(set(ids)) == len(ids)
    assert any("Weeknd" in item[2] for item in curated_audio.CURATED)
    assert any(item[2] == "SLOWBURN" for item in curated_audio.CURATED)


def test_audio_url_from_dash_manifest():
    info = {"dash_manifest":
            '<MPD><BaseURL>https://cdn/x.mp4?a=1&amp;b=2</BaseURL></MPD>'}
    assert curated_audio._audio_url(info) == "https://cdn/x.mp4?a=1&b=2"


def test_pick_uses_least_recently_used_and_returns_metadata(monkeypatch, tmp_path):
    first = curated_audio.CURATED[0]
    second = curated_audio.CURATED[1]
    for tid, _title, _artist in curated_audio.CURATED:
        db.set_state(f"music:curated:{tid}", "0")
    db.set_state(f"music:curated:{first[0]}", "9999999999")

    manifest = '<MPD><BaseURL>https://cdn/x.mp4</BaseURL></MPD>'
    monkeypatch.setattr(
        curated_audio, "_music_asset",
        lambda cl, tid: {"title": "Song " + tid,
                         "display_artist": "Artist",
                         "audio_cluster_id": "cluster",
                         "dash_manifest": manifest,
                         "highlight_start_times_in_ms": [5000]},
    )
    cached = tmp_path / "audio.m4a"
    cached.write_bytes(b"x" * 30000)
    monkeypatch.setattr(curated_audio, "_download", lambda *a, **k: cached)

    result = curated_audio.pick_curated_track(MagicMock())
    assert result["track_id"] == second[0]
    assert result["source"] == "curated_catalog"
    assert result["title"].startswith("Song ")
    assert result["credit"].startswith("Music: ")


def test_dead_ids_are_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(curated_audio, "_music_asset", lambda cl, tid: None)
    assert curated_audio.pick_curated_track(MagicMock()) is None
