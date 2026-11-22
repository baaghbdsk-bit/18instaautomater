"""Catalog audio URL extraction for guaranteed-audible Reels."""

from types import SimpleNamespace

import audio_mux


def test_audio_url_prefers_progressive():
    track = SimpleNamespace(
        progressive_download_url="https://cdn.example/a.mp4?token=1",
        dash_manifest="",
    )
    assert audio_mux.audio_url(track) == "https://cdn.example/a.mp4?token=1"


def test_audio_url_falls_back_to_dash_manifest():
    manifest = '<MPD><BaseURL>https://cdn.example/a.mp4?a=1&amp;b=2</BaseURL></MPD>'
    track = SimpleNamespace(progressive_download_url=None,
                            dash_manifest=manifest)
    assert audio_mux.audio_url(track) == "https://cdn.example/a.mp4?a=1&b=2"


def test_audio_url_raises_without_url():
    import pytest

    with pytest.raises(RuntimeError):
        audio_mux.audio_url(SimpleNamespace(
            progressive_download_url=None, dash_manifest=""))


def test_highlight_start_seconds():
    track = SimpleNamespace(highlight_start_times_in_ms=[82500, 110500])
    assert audio_mux.highlight_start_seconds(track) == 82.5
    assert audio_mux.highlight_start_seconds(
        SimpleNamespace(highlight_start_times_in_ms=[])) == 0.0
