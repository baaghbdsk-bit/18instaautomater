"""
validate.py — pre-publish MP4 validation (port of the reference video.js).

Defense in depth: a broken render must never reach Instagram. Checks size,
codec, pixel format, resolution, audio, duration, and that the moov atom
precedes mdat (faststart) using a hand-rolled MP4 box walker.
"""

import json
import struct
import subprocess
from pathlib import Path
from typing import Tuple

from config import FFPROBE_BIN, VIDEO_WIDTH, VIDEO_HEIGHT

MIN_BYTES = 150 * 1024          # 150 KB — a failed render is usually ~0 bytes
MAX_BYTES = 100 * 1024 * 1024   # 100 MB — IG limit
MIN_SECONDS = 7
MAX_SECONDS = 18


def probe(path) -> dict:
    """ffprobe JSON for the file; raises on failure."""
    cmd = [
        FFPROBE_BIN, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr[:300]}")
    return json.loads(out.stdout or "{}")


def faststart(path) -> bool:
    """
    True when the moov atom appears before mdat in the first 1 MB.
    Instagram needs faststart; a non-faststart file may fail to publish.
    """
    try:
        size = Path(path).stat().st_size
        with open(path, "rb") as fh:
            data = fh.read(min(size, 1_048_576))
    except OSError:
        return False

    offset = 0
    seen = []
    while offset + 8 <= len(data):
        box_size, box_type = struct.unpack(">I4s", data[offset:offset + 8])
        try:
            btype = box_type.decode("ascii")
        except UnicodeDecodeError:
            break
        if box_size == 1:                       # 64-bit largesize
            if offset + 16 > len(data):
                break
            box_size = struct.unpack(">Q", data[offset + 8:offset + 16])[0]
        elif box_size == 0:                     # box extends to EOF
            box_size = len(data) - offset
        if box_size < 8:
            break
        seen.append(btype)
        if btype == "moov":
            return "mdat" not in seen
        if btype == "mdat":
            return False
        offset += box_size
    return False


def validate_video(path, width: int = VIDEO_WIDTH, height: int = VIDEO_HEIGHT,
                   min_seconds: float = MIN_SECONDS,
                   max_seconds: float = MAX_SECONDS) -> Tuple[bool, list, dict]:
    """Returns (ok, reasons, info). Reasons are safe to print in public logs."""
    reasons = []
    info: dict = {}
    p = Path(path)
    if not p.exists():
        return False, ["file does not exist"], info

    size = p.stat().st_size
    info["bytes"] = size
    if size < MIN_BYTES:
        reasons.append(f"file too small ({size} bytes)")
    if size > MAX_BYTES:
        reasons.append(f"file over 100 MB ({size} bytes)")

    try:
        data = probe(p)
    except Exception as e:  # noqa: BLE001
        return False, reasons + [f"ffprobe failed: {e}"], info

    streams = data.get("streams", [])
    vstreams = [s for s in streams if s.get("codec_type") == "video"]
    astreams = [s for s in streams if s.get("codec_type") == "audio"]
    if not vstreams:
        reasons.append("no video stream")
    if not astreams:
        reasons.append("no audio stream")

    if vstreams:
        v = vstreams[0]
        info["codec"] = v.get("codec_name")
        info["pix_fmt"] = v.get("pix_fmt")
        info["width"] = v.get("width")
        info["height"] = v.get("height")
        if v.get("codec_name") != "h264":
            reasons.append(f"video codec is {v.get('codec_name')}, need h264")
        if v.get("pix_fmt") not in ("yuv420p", "yuvj420p"):
            reasons.append(f"pix_fmt {v.get('pix_fmt')}, need yuv420p")
        if v.get("width") != width or v.get("height") != height:
            reasons.append(
                f"resolution {v.get('width')}x{v.get('height')}, "
                f"need {width}x{height}")

    if astreams:
        info["audio_codec"] = astreams[0].get("codec_name")
        if astreams[0].get("codec_name") != "aac":
            reasons.append(f"audio codec is {astreams[0].get('codec_name')}, need aac")

    try:
        duration = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        duration = 0.0
    info["duration"] = round(duration, 2)
    if not (min_seconds <= duration <= max_seconds):
        reasons.append(
            f"duration {duration:.1f}s outside {min_seconds:.0f}-{max_seconds:.0f}s")

    if not faststart(p):
        reasons.append("moov atom is not before mdat (need +faststart)")

    return not reasons, reasons, info
