"""Tests for MP4 validation and the faststart box walker (no network)."""

import struct

import pytest

from validate import faststart, validate_video


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def test_missing_file(tmp_path):
    ok, reasons, info = validate_video(tmp_path / "nope.mp4")
    assert ok is False
    assert "file does not exist" in reasons


def test_faststart_moov_before_mdat(tmp_path):
    p = tmp_path / "good.mp4"
    p.write_bytes(_box(b"ftyp", b"isom") + _box(b"moov", b"x" * 16)
                  + _box(b"mdat", b"y" * 64))
    assert faststart(p) is True


def test_faststart_mdat_before_moov(tmp_path):
    p = tmp_path / "bad.mp4"
    p.write_bytes(_box(b"ftyp", b"isom") + _box(b"mdat", b"y" * 64)
                  + _box(b"moov", b"x" * 16))
    assert faststart(p) is False


def test_faststart_rejects_tiny_or_missing(tmp_path):
    assert faststart(tmp_path / "none.mp4") is False
    p = tmp_path / "junk.mp4"
    p.write_bytes(b"not an mp4 at all, really")
    assert faststart(p) is False


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None
                    and not __import__("pathlib").Path(
                        __import__("config").FFMPEG_BIN).exists(),
                    reason="ffmpeg not available")
def test_validate_real_render(tmp_path):
    """Opt-in-style real render: 1s silent clip must pass structural checks."""
    import subprocess
    from config import FFMPEG_BIN
    out = tmp_path / "clip.mp4"
    subprocess.run(
        [FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=1:r=30",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-t", "1", "-movflags", "+faststart", str(out)],
        check=True, timeout=120)
    ok, reasons, info = validate_video(out)
    assert ok is False          # 1s is below MIN_SECONDS by design
    assert any("duration" in r for r in reasons)
    assert info["codec"] == "h264"
    assert info["width"] == 1080 and info["height"] == 1920
