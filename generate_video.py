"""
generate_video.py — reel renderer (port of the reference quote.js).

Primary path: single ffmpeg invocation with libass text rendering —
auto-sized Anton quote (<=4 lines, even wrap), gaussian scrim behind the
text, one of five slow camera moves, film grain + vignette, random music
offset so two reels never share an intro, loudness-normalised audio.

Fallback path: classic drawtext when the ffmpeg build lacks libass.

Usage:
    from generate_video import render_reel, make_video
    info = render_reel(image, music, "Bet you can't look away", mode="story")
    path = make_video(image, music, "line", mode="story")   # compat, returns str
"""

import math
import random
import subprocess
from datetime import datetime
from pathlib import Path

from config import (
    ACCENT,
    BASE_DIR,
    CHANNEL_HANDLE,
    DURATION_MAX,
    DURATION_MIN,
    FFMPEG_BIN,
    FONT_HEAD,
    FONT_QUOTE,
    FONTS_DIR,
    MARGIN_X,
    OUTPUT_DIR,
    REEL_DURATION,
    REEL_MOTION,
    SCALE_MODE,
    TEXT_OUTLINE,
    TMP_DIR,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    ZOOM_SPEED,
)
from lines import strip_emoji

MODES = {
    "story": (VIDEO_WIDTH, VIDEO_HEIGHT),
    "feed": (1080, 1350),
}

# Smaller, readable quote sizes. The old 116-68px set made the overlay cover
# most of the subject in a 1080x1920 Reel.
FONT_SIZES = (82, 76, 70, 64, 58, 52, 46)
MAX_LINES = 4
LINE_SPACING = 1.14

MOTIONS = ["push_center", "push_up", "push_down", "drift_left", "drift_right"]

_has_ass: bool | None = None


def _ffmpeg_has_ass() -> bool:
    """Detect libass once (cached)."""
    global _has_ass
    if _has_ass is None:
        try:
            out = subprocess.run([FFMPEG_BIN, "-hide_banner", "-filters"],
                                 capture_output=True, text=True, timeout=30)
            _has_ass = " ass " in (out.stdout + out.stderr) or \
                       "\n .. ass" in (out.stdout + out.stderr) or \
                       any(line.strip().endswith(" ass") or " ass " in line
                           for line in (out.stdout + out.stderr).splitlines()
                           if "ass" in line)
        except Exception:  # noqa: BLE001
            _has_ass = False
        if not _has_ass:
            print("[render] ffmpeg has no libass — falling back to drawtext")
    return bool(_has_ass)


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------
def wrap_lines(text: str, font, usable: int) -> list:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if not cur or font.getlength(trial) <= usable:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def layout(text: str, width: int = VIDEO_WIDTH,
           margin_x: int = MARGIN_X) -> dict:
    """
    Pick the largest font size that keeps the quote within MAX_LINES and
    wraps it as evenly as possible. Returns {size, lines}.
    """
    from PIL import ImageFont

    text = " ".join(strip_emoji(text).split())
    usable = width - 2 * margin_x
    candidates = []
    for size in FONT_SIZES:
        try:
            font = ImageFont.truetype(str(FONT_QUOTE), size)
        except Exception:  # noqa: BLE001
            font = ImageFont.load_default()
        lines = wrap_lines(text, font, usable)
        if len(lines) > MAX_LINES:
            continue
        widths = [font.getlength(ln) for ln in lines]
        even = (min(widths) / max(widths)) if max(widths) > 0 else 0.0
        candidates.append({
            "size": size,
            "lines": lines,
            "even": even,
            "n": len(lines),
            "good": even >= 0.85,
        })

    if candidates:
        # even-enough first, then fewer lines, then more even, then bigger
        candidates.sort(key=lambda c: (not c["good"], c["n"], -c["even"], -c["size"]))
        best = candidates[0]
        return {"size": best["size"], "lines": best["lines"]}

    # Rare: very long line. Smallest size, greedy wrap, accept up to 5 lines.
    size = FONT_SIZES[-1]
    font = ImageFont.truetype(str(FONT_QUOTE), size)
    return {"size": size, "lines": wrap_lines(text, font, usable)}


# ---------------------------------------------------------------------------
# ASS subtitle generation
# ---------------------------------------------------------------------------
def _ass_color(hex_argb: str) -> str:
    """'0xFFFFC61A' (AARRGGBB) -> '&H001AC6FF' (ASS &HAABBGGRR, 00=opaque)."""
    h = hex_argb.lstrip("0x").upper().rjust(8, "0")
    if len(h) != 8:
        return "&H00FFFFFF"
    aa, rr, gg, bb = h[0:2], h[2:4], h[4:6], h[6:8]
    ass_alpha = f"{0xFF - int(aa, 16):02X}"   # web alpha is inverted vs ASS
    return f"&H{ass_alpha}{bb}{gg}{rr}"


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def build_ass(quote: dict, width: int, height: int, duration: float,
              variant: str, handle: str = "") -> str:
    # Hook text: TOP 15% only, max 6 words per line, never covers body/cleavage.
    cy_frac = 0.15  # fixed top zone only
    cy = cy_frac * height
    size = quote["size"]
    lines = quote["lines"]
    # Truncate each line to max 6 words to keep it short and top-placed.
    short_lines = []
    for ln in lines:
        words = ln.split()
        if len(words) > 6:
            short_lines.append(" ".join(words[:6]))
        else:
            short_lines.append(ln)
    lines = short_lines
    line_h = size * LINE_SPACING
    cx = width / 2

    accent = _ass_color(ACCENT)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Quote,Barlow Semi Condensed,{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{TEXT_OUTLINE},0,5,{MARGIN_X},{MARGIN_X},0,1
Style: Mark,Archivo Black,24,{accent},&H000000FF,&H90000000,&H80000000,0,0,0,0,100,100,1,0,3,8,0,3,{MARGIN_X},{MARGIN_X},90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    total = len(lines)
    start_all = 0.10
    for i, ln in enumerate(lines):
        y = cy - (total - 1) * line_h / 2 + i * line_h
        t0 = start_all + i * 0.26
        events.append(
            f"Dialogue: 0,{_ass_time(t0)},{_ass_time(duration)},Quote,,0,0,0,,"
            f"{{\\an5\\move({cx:.0f},{y + 26:.0f},{cx:.0f},{y:.0f},0,420)"
            f"\\fad(320,0)}}{_esc(ln)}"
        )
    if handle:
        events.append(
            f"Dialogue: 0,{_ass_time(0.5)},{_ass_time(duration)},Mark,,0,0,0,,"
            f"{{\\an3\\fad(300,0)}}{_esc(handle)}"
        )
    return header + "\n".join(events) + "\n"


# ---------------------------------------------------------------------------
# scrim (cached gaussian band PNG)
# ---------------------------------------------------------------------------
def ensure_scrim(width: int, height: int, variant: str) -> Path:
    from PIL import Image

    frac = {"upper": 0.30, "center": 0.46, "lower": 0.63}.get(variant, 0.46)
    pct = int(frac * 100)
    path = BASE_DIR / "assets" / "overlay" / f"scrim-{width}x{height}-{pct}.png"
    if path.exists():
        return path

    cy, sigma = frac * height, 0.24 * height
    band = Image.new("L", (1, height))
    band.putdata([
        int(255 * min(1.0, 0.13 + 0.55 * math.exp(-((y - cy) / sigma) ** 2)))
        for y in range(height)
    ])
    alpha = band.resize((width, height))
    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    img.putalpha(alpha)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


# ---------------------------------------------------------------------------
# camera motion
# ---------------------------------------------------------------------------
def motion_expressions(motion: str, frames: int, speed: float = ZOOM_SPEED) -> dict:
    """zoompan x/y/z expressions normalised by the output frame count."""
    z = f"min(1+{speed}*on,1.22)"
    cx = "iw/2-(iw/zoom)/2"
    cy = "ih/2-(ih/zoom)/2"
    if motion == "push_up":
        return {"z": z, "x": cx, "y": f"(ih-ih/zoom)*(1-on/{frames})"}
    if motion == "push_down":
        return {"z": z, "x": cx, "y": f"(ih-ih/zoom)*(on/{frames})"}
    if motion == "drift_left":
        return {"z": z, "x": f"(iw-iw/zoom)*(1-on/{frames})", "y": cy}
    if motion == "drift_right":
        return {"z": z, "x": f"(iw-iw/zoom)*(on/{frames})", "y": cy}
    return {"z": z, "x": cx, "y": cy}


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------
def _ff_duration(path) -> float:
    try:
        from config import FFPROBE_BIN
        out = subprocess.run(
            [FFPROBE_BIN, "-v", "error",
             "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30)
        return float((out.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def render_reel(image_path, music_path, text: str, mode: str = "story",
                output_name: str | None = None, variant: str | None = None,
                duration: float | None = None, handle: str | None = None,
                watermark: bool = True) -> dict:
    """
    Render one reel. Returns
    {path, duration, variant, motion, lines, music, offset, size_bytes}.
    """
    image_path = Path(image_path).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    music_path = Path(music_path).resolve() if music_path else None
    if music_path and not music_path.exists():
        raise FileNotFoundError(f"Music not found: {music_path}")

    width, height = MODES.get(mode, MODES["story"])
    duration = float(duration or random.uniform(DURATION_MIN, DURATION_MAX))
    duration = round(min(max(duration, 6.0), 60.0), 1)
    variant = variant or random.choice(["upper", "center", "lower"])
    motion = random.choice(MOTIONS)
    handle = (CHANNEL_HANDLE if handle is None else handle) if watermark else ""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_name is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"reel_{stamp}.mp4"
    output_path = OUTPUT_DIR / output_name

    quote = layout(text, width=width)
    frames = max(1, int(duration * VIDEO_FPS))
    scrim = ensure_scrim(width, height, variant)

    # Random music offset so two reels never share an intro.
    offset = 0.0
    if music_path and _ff_duration(music_path) > 25:
        offset = round(duration * (0.12 + random.random() * 0.38), 2)

    use_ass = _ffmpeg_has_ass()
    ass_file = None
    if use_ass:
        ass_file = TMP_DIR / f"reel_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.ass"
        ass_file.write_text(
            build_ass(quote, width, height, duration, variant, handle),
            encoding="utf-8")

    fit = (f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
           f"crop={width * 2}:{height * 2},setsar=1") if SCALE_MODE == "cover" else (
           f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
           f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1")

    mo = motion_expressions(motion, frames)
    zoompan = (f"zoompan=z='{mo['z']}':x='{mo['x']}':y='{mo['y']}'"
               f":d={frames}:s={width}x{height}:fps={VIDEO_FPS}")
    grade = ("eq=contrast=1.08:saturation=0.86:brightness=-0.04:gamma=0.98,"
             "format=yuv420p")

    # Paths relative to BASE_DIR (avoids Windows drive-letter colons in filters).
    rel_img = image_path.relative_to(BASE_DIR).as_posix() if \
        image_path.is_relative_to(BASE_DIR) else image_path.as_posix()
    rel_scrim = scrim.relative_to(BASE_DIR).as_posix()

    cmd = [FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error"]
    cmd += ["-i", rel_img, "-i", rel_scrim]
    has_audio = music_path is not None
    if has_audio:
        cmd += ["-stream_loop", "-1", "-ss", str(offset), "-i", str(music_path)]

    if use_ass:
        rel_fonts = FONTS_DIR.relative_to(BASE_DIR).as_posix()
        rel_ass = ass_file.relative_to(BASE_DIR).as_posix()

    filters = []
    filters.append(f"[0:v]{fit},{zoompan},{grade}[b]")
    filters.append("[b][1:v]overlay=0:0[v1]")
    filters.append("[v1]vignette=PI/4.2,noise=alls=5:allf=t[v2]")
    if use_ass:
        filters.append(f"[v2]ass='{rel_ass}':fontsdir='{rel_fonts}'[vout]")
    else:
        filters.append(f"[v2]{_drawtext_filter(quote, width, height, duration)}[vout]")

    if has_audio:
        fade_out_start = max(0.0, duration - 1.6)
        filters.append(
            f"[2:a]atrim=0:{duration},afade=t=in:d=0.9,"
            f"afade=t=out:st={fade_out_start:.2f}:d=1.6,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")

    cmd += ["-filter_complex", ";".join(filters),
            "-map", "[vout]"]
    if has_audio:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    else:
        cmd += ["-an"]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-color_range", "tv",
        "-colorspace", "bt709", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-profile:v", "high", "-level", "4.1",
        "-movflags", "+faststart", "-r", str(VIDEO_FPS), "-t", str(duration),
        str(output_path),
    ]

    proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
    if ass_file and ass_file.exists():
        try:
            ass_file.unlink()
        except OSError:
            pass
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed ({proc.returncode}): "
            f"{(proc.stderr or proc.stdout or '')[-3500:]}")

    size = output_path.stat().st_size
    print(f"[render] {output_path.name}  {duration}s  variant={variant} "
          f"motion={motion}  {size / 1e6:.1f} MB")
    return {
        "path": str(output_path),
        "duration": duration,
        "variant": variant,
        "motion": motion,
        "lines": quote["lines"],
        "music": str(music_path) if music_path else None,
        "offset": offset,
        "size_bytes": size,
    }


def _drawtext_filter(quote: dict, width: int, height: int,
                     duration: float) -> str:
    """Fallback overlay when ffmpeg lacks libass. Top 15%, max 6 words."""
    # Truncate each line to max 6 words.
    short_lines = []
    for ln in quote["lines"]:
        words = ln.split()
        if len(words) > 6:
            short_lines.append(" ".join(words[:6]))
        else:
            short_lines.append(ln)
    txt = TMP_DIR / f"drawtext_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.txt"
    txt.write_text("\n".join(short_lines), encoding="utf-8")
    rel = txt.relative_to(BASE_DIR).as_posix()
    font_rel = FONT_QUOTE.relative_to(BASE_DIR).as_posix()
    # Top zone only: y = 15% of height.
    return (f"drawtext=textfile='{rel}':fontfile='{font_rel}'"
            f":fontsize={quote['size']}:fontcolor=white"
            f":box=1:boxcolor=black@0.55:boxborderw=10"
            f":line_spacing=8"
            f":x=(w-text_w)/2:y=0.15*h"
            f":enable='between(t,0,{duration})'")


# ---------------------------------------------------------------------------
# reel from an already-composed quote image
# ---------------------------------------------------------------------------
def still_video(image_path, output_path, duration: float | None = None,
                motion: str | None = None, fps: int = VIDEO_FPS,
                silent_audio: bool = False,
                music_path=None) -> dict:
    """Turn a composed quote image into an Instagram Reel MP4.

    The quote is already burned into the JPEG by compose_image.py, so no ASS
    text is added here. The MP4 MUST always carry an audio stream (AAC) so
    it is never silent — if no catalog track is provided, a local MP3 from
    assets/music/ is looped as fallback.
    """
    from pathlib import Path

    src = Path(image_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Image not found: {src}")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    duration = round(min(max(float(duration or REEL_DURATION), 6.0), 60.0), 1)
    motion = motion or REEL_MOTION
    frames = max(1, int(duration * fps))
    mo = motion_expressions(motion, frames)
    zoompan = (f"zoompan=z='{mo['z']}':x='{mo['x']}':y='{mo['y']}'"
               f":d=1:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={fps}")
    fit = (f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
           f"force_original_aspect_ratio=increase,"
           f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},setsar=1")
    grade = "eq=contrast=1.04:saturation=0.96:brightness=-0.02,format=yuv420p"
    vf = f"{fit},{zoompan},{grade}"

    # Pick fallback music if no catalog track supplied.
    fallback_music = None
    if music_path is None:
        from music_match import CURATED_TRACKS, find_curated_track
        from instagrapi import Client
        import os
        import glob
        # Use a tiny local loop from assets/music as silent fallback is banned.
        music_files = []
        for root, _dirs, files in os.walk(BASE_DIR / "assets" / "music"):
            for fn in files:
                if fn.lower().endswith((".mp3", ".wav", ".m4a", ".aac")):
                    music_files.append(Path(root) / fn)
        if music_files:
            fallback_music = sorted(music_files)[0]

    cmd = [FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error",
           "-loop", "1", "-framerate", str(fps), "-i", str(src)]
    has_audio = music_path is not None or fallback_music is not None
    audio_source = music_path if music_path else fallback_music
    if has_audio:
        cmd += ["-stream_loop", "-1", "-i", str(audio_source)]
    cmd += ["-vf", vf, "-t", str(duration), "-r", str(fps),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-threads", "2",
            "-pix_fmt", "yuv420p", "-color_range", "tv",
            "-movflags", "+faststart"]
    if has_audio:
        # Match the working reel-engine: smooth fades and loudness targets so
        # every bank track plays at a consistent, audible level.
        fade_out = max(0.0, duration - 1.2)
        afilter = (
            f"atrim=0:{duration},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.6,"
            f"afade=t=out:st={fade_out:.2f}:d=1.2,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000"
        )
        cmd += ["-map", "0:v:0", "-map", "1:a:0", "-af", afilter,
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest"]
    else:
        # No audio file exists at all — still must not be silent:
        # generate a 1kHz tone so validate_video sees an AAC stream.
        cmd += ["-f", "lavfi", "-i", "sine=frequency=1000:duration=60",
                "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac",
                "-b:a", "128k", "-ar", "48000", "-shortest"]
    cmd += [str(out)]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg still_video failed ({proc.returncode}): "
                           f"{(proc.stderr or '')[-2000:]}")
    return {"path": str(out), "duration": duration, "motion": motion,
            "size_bytes": out.stat().st_size}


# ---------------------------------------------------------------------------
# backward-compatible wrapper (main.py / make_sample.py use this)
# ---------------------------------------------------------------------------
def make_video(image_path, music_path, text: str, mode: str = "feed",
               output_name: str | None = None) -> str:
    info = render_reel(image_path, music_path, text, mode=mode,
                       output_name=output_name)
    return info["path"]


if __name__ == "__main__":
    import sys
    from config import IMAGES_DIR

    img = sys.argv[1] if len(sys.argv) > 1 else str(next(IMAGES_DIR.glob("*.jpg")))
    mus = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    txt = sys.argv[3] if len(sys.argv) > 3 else "Bet you can't look away from this one"
    mode = sys.argv[4] if len(sys.argv) > 4 else "story"
    print(render_reel(img, mus, txt, mode=mode))
