"""
config.py — central configuration for the reel engine.

Everything tunable lives here or in .env. Text lines / captions / hashtags
live in lines.py, content themes live in themes.py.
"""

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Paths (all auto-created)
# ---------------------------------------------------------------------------
ASSETS_DIR = BASE_DIR / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
MUSIC_DIR = ASSETS_DIR / "music"
FONTS_DIR = ASSETS_DIR / "fonts"
OUTPUT_DIR = ASSETS_DIR / "output"
OVERLAY_DIR = ASSETS_DIR / "overlay"   # generated scrims (cached)
TMP_DIR = ASSETS_DIR / "tmp"           # ephemeral render workdirs
DATA_DIR = BASE_DIR / "data"           # SQLite state (committed by CI)
SESSIONS_DIR = BASE_DIR / "sessions"   # instagrapi session cookies (never committed)

for _d in (IMAGES_DIR, MUSIC_DIR, FONTS_DIR, OUTPUT_DIR, OVERLAY_DIR,
           TMP_DIR, DATA_DIR, SESSIONS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "engine.db"

# ---------------------------------------------------------------------------
# Instagram accounts (rotation) — add account 2/3 via env when ready
# ---------------------------------------------------------------------------
ACCOUNTS = [
    {
        "name": "account_1",
        "username": os.getenv("IG_USERNAME_1", ""),
        "password": os.getenv("IG_PASSWORD_1", ""),
        "two_factor_secret": os.getenv("IG_2FA_SECRET_1", ""),
        "handle": os.getenv("IG_HANDLE_1") or "@xene.ai",
    },
    {
        "name": "account_2",
        "username": os.getenv("IG_USERNAME_2", ""),
        "password": os.getenv("IG_PASSWORD_2", ""),
        "two_factor_secret": os.getenv("IG_2FA_SECRET_2", ""),
        "handle": os.getenv("IG_HANDLE_2") or "",
    },
]

# Public watermark handle drawn on every reel ("" disables it).
CHANNEL_HANDLE = os.getenv("IG_HANDLE_1") or "@xene.ai"

# ---------------------------------------------------------------------------
# Schedule / cadence guards
# ---------------------------------------------------------------------------
# Minimum minutes between two publishes (any account).
MIN_GAP_MINUTES = int(os.getenv("MIN_GAP_MINUTES", "120"))
# Per-UTC-day publish cap per account.
DAILY_CAP_PER_ACCOUNT = int(os.getenv("DAILY_CAP_PER_ACCOUNT", "6"))
# Local multi-post mode (main.py) pacing.
POST_INTERVAL_MIN = int(os.getenv("POST_INTERVAL_MIN", "900"))
POST_INTERVAL_MAX = int(os.getenv("POST_INTERVAL_MAX", "1800"))
MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "6"))

# ---------------------------------------------------------------------------
# LLM (OpenAI-compatible endpoint — Gemini by default) for line generation
# ---------------------------------------------------------------------------
LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODELS = [m.strip() for m in os.getenv(
    "LLM_MODEL", "gemini-3-flash-preview,gemini-3.6-flash,gemini-3.8-flash"
).split(",") if m.strip()]

# ---------------------------------------------------------------------------
# ffmpeg / ffprobe
# ---------------------------------------------------------------------------
_DEFAULT_FFMPEG = (
    r"C:\Users\gvive\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
)
FFMPEG_BIN = os.getenv("FFMPEG_BIN") or (
    "ffmpeg" if shutil.which("ffmpeg") else _DEFAULT_FFMPEG
)


def _sibling_binary(name: str) -> str:
    """Resolve ffprobe next to a resolved ffmpeg, else PATH, else bare name."""
    if os.path.sep in FFMPEG_BIN or (os.path.altsep and os.path.altsep in FFMPEG_BIN):
        cand = Path(FFMPEG_BIN).parent / (name + (".exe" if os.name == "nt" else ""))
        if cand.exists():
            return str(cand)
    return shutil.which(name) or name


FFPROBE_BIN = os.getenv("FFPROBE_BIN") or _sibling_binary("ffprobe")

# ---------------------------------------------------------------------------
# Video rendering
# ---------------------------------------------------------------------------
VIDEO_WIDTH, VIDEO_HEIGHT = 1080, 1920      # 9:16 reel
VIDEO_FPS = 30
DURATION_MIN = float(os.getenv("DURATION_MIN", "9"))    # seconds
DURATION_MAX = float(os.getenv("DURATION_MAX", "15"))
SCALE_MODE = os.getenv("SCALE_MODE", "cover")           # cover | contain
ZOOM_SPEED = float(os.getenv("ZOOM_SPEED", "0.0007"))   # zoompan step per frame

# Fonts (Anton for quotes, Archivo Black for watermark/labels)
FONT_QUOTE = FONTS_DIR / "Anton-Regular.ttf"
FONT_HEAD = FONTS_DIR / "ArchivoBlack-Regular.ttf"

# Text placement: fraction of frame height where the block centre sits.
VARIANTS = {"upper": 0.30, "center": 0.46, "lower": 0.63}
VARIANT_KEYS = ["upper", "center", "lower"]

# ASS accent colour (AARRGGBB) + outline
ACCENT = os.getenv("ACCENT", "0xFFFFC61A")
TEXT_OUTLINE = 4
MARGIN_X = 88

# ---------------------------------------------------------------------------
# Image generation (Perchance wrapper)
# ---------------------------------------------------------------------------
PERCHANCE_URL = os.getenv("PERCHANCE_URL", "http://127.0.0.1:8000")
PERCHANCE_STYLE = os.getenv("PERCHANCE_STYLE", "Cinematic")
PERCHANCE_ASPECT = os.getenv("PERCHANCE_ASPECT", "512x768")
PERCHANCE_GUIDANCE = float(os.getenv("PERCHANCE_GUIDANCE", "7"))
# Hard safety net — never generate explicit material (IG bans fast).
PERCHANCE_NEGATIVE = os.getenv(
    "PERCHANCE_NEGATIVE",
    "nude, naked, explicit, porn, sexual, NSFW, underwear, lingerie, "
    "see-through, topless, cleavage",
)

# Music licensing (CC BY 4.0 requires attribution in the caption).
MUSIC_CREDIT_IN_CAPTION = os.getenv("MUSIC_CREDIT_IN_CAPTION", "1") == "1"
MUSIC_CREDIT = ("Music: Kevin MacLeod (incompetech.com) — CC BY 4.0")

# ---------------------------------------------------------------------------
# Reliability / safety switches
# ---------------------------------------------------------------------------
KILL_SWITCH = os.getenv("KILL_SWITCH", "0") == "1"
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
RANDOM_SEED = os.getenv("RANDOM_SEED") or None

# Failure notification (optional Discord/Slack webhook).
NOTIFY_WEBHOOK_URL = os.getenv("NOTIFY_WEBHOOK_URL", "")

# Keep the LLM line generator honest about the niche.
CONTENT_NICHE = os.getenv(
    "CONTENT_NICHE",
    "flirty and suggestive glamour content for an AI-model Instagram page",
)
