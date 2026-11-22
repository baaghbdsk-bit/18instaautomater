"""
audio_mux.py — put the chosen catalog track's audio into the Reel MP4.

Instagram correctly registers the track as licensed_music in media metadata,
but playback can still be silent because the uploaded MP4 itself has no audio
stream. Muxing the same catalog audio into the file guarantees it is audible
regardless of how the Instagram client applies the metadata.
"""

import re
import subprocess
from pathlib import Path

from config import FFMPEG_BIN, TMP_DIR


def audio_url(track) -> str:
    """Get a playable URL for the track's audio from an instagrapi Track."""
    url = getattr(track, "progressive_download_url", None)
    if url:
        return str(url)
    manifest = getattr(track, "dash_manifest", "") or ""
    match = re.search(r"<BaseURL>(.*?)</BaseURL>", manifest, re.DOTALL)
    if match:
        return match.group(1).replace("&amp;", "&")
    raise RuntimeError("catalog track has no audio URL")


def highlight_start_seconds(track) -> float:
    times = getattr(track, "highlight_start_times_in_ms", None) or []
    return (int(times[0]) / 1000.0) if times else 0.0


def mux_track_audio(video_path, track, duration: float) -> dict:
    """Mux the catalog track into the video, starting at its highlight."""
    source = Path(video_path)
    if not source.exists():
        raise RuntimeError(f"reel video missing: {source}")
    url = audio_url(track)
    out = TMP_DIR / f"muxed_{source.stem}.mp4"
    start = highlight_start_seconds(track)
    cmd = [
        FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-i", url,
        "-i", str(source),
        "-filter_complex",
        f"[0:a]atrim=0:{max(duration, 1)},asetpts=PTS-STARTPTS[a]",
        "-map", "1:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(out),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except OSError as e:
        raise RuntimeError(f"ffmpeg could not mux audio from {url}: {e}") from e
    if proc.returncode != 0 or not out.exists() or out.stat().st_size < 10000:
        raise RuntimeError(
            f"audio mux FATAL (rc {proc.returncode}) url={url}: "
            f"{(proc.stderr or '')[-2000:]}")
    return {"path": str(out), "start_sec": start}
