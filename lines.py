"""
lines.py — quote lines + captions with three-level dedupe (port of lines.js).

Order of business for a fresh line:
  1. unused LLM-generated line for the theme
  2. ask the LLM for new ones (Gemini, OpenAI-compatible), filter hard
  3. hand-written seed pool for the mood
  4. recycle the least-recently-used seed (never fails)

Dedupe: exact (unique norm) -> near-duplicate (Jaccard >= 0.62) -> already
posted (used_assets). Clichés and non-Roman/emoji lines are rejected outright.
"""

import json
import random
import re
import string
from typing import List, Optional, Set

import db
import notify
import net
from config import (
    CONTENT_NICHE,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODELS,
)

# ---------------------------------------------------------------------------
# Seed bank — 3 moods x 30 hand-written lines (offline fallback, never fails)
# Suggestive/flirty only: no explicit language (IG bans fast).
# ---------------------------------------------------------------------------
SEED = {
    "flirty": [
        "Bet you can't look away from this one",
        "You scrolled this far, so stay a while",
        "Closer than you think, darling",
        "Save this one for later tonight",
        "Your screen just got a lot hotter",
        "Miss me yet? Be honest about it",
        "I know you're staring, it's fine",
        "This one is just for you, obviously",
        "Don't tell anyone you found me here",
        "You were supposed to keep scrolling",
        "Still watching? I like your style",
        "Imagine I was your only notification",
        "Late night and you're still here",
        "One more look won't hurt anyone",
        "You keep coming back, I see you",
        "Screenshot it, I won't mind at all",
        "The mood you can't scroll past twice",
        "Careful, this one gets addictive fast",
        "Wrong time, right feeling, keep watching",
        "Tap the profile before you disappear",
        "Stay a little longer, it gets better",
        "Only the brave ones keep watching",
        "You look like you need a distraction",
        "I'd reply instantly, just saying so",
        "Consider this your sign to follow",
        "Watch it twice, I won't judge you",
        "Got a minute? I'm worth every second",
        "Nobody has to know you liked this one",
        "Your favorite reason to procrastinate",
        "Follow now, thank me tomorrow morning",
    ],
    "bold": [
        "Confidence looks this good on me",
        "I don't chase, I simply attract",
        "Watch me, then watch me win anyway",
        "Not everyone can handle this energy",
        "Set the bar and I'll step over it",
        "Main character energy only from here",
        "You couldn't survive half my day",
        "Loud, proud and completely unbothered",
        "I am the plot twist you didn't expect",
        "The standard, in case you were asking",
        "Catch me if you possibly can keep up",
        "They wanted humble, I gave them iconic",
        "Every scroll deserves a real star",
        "Built different and doing it on purpose",
        "Know your worth, then add compound interest",
        "I woke up like this, obviously always",
        "Half-hearted effort doesn't interest me",
        "Too focused to be worried about copying",
        "Make them stare, then smile at them",
        "Pressure makes diamonds and I'm sparkling",
        "I don't fit in, I simply stand out",
        "Effortless is my entire aesthetic",
        "Keep up or keep quiet about it",
        "The algorithm has a crush on me",
        "Drama-free, thriving and too busy",
        "Eyes up here, always and only here",
        "I turned every no into a runway",
        "Rare, valuable and fully aware of it",
        "Born to shine through anything at all",
        "Winning quietly speaks the loudest here",
    ],
    "dreamy": [
        "Lost in a daydream about you again",
        "Soft heart with very sharp eyes",
        "Meet me where the sky turns pink",
        "Somewhere between asleep and thinking",
        "Golden hour never looked quite like this",
        "Drifting away on a warm summer breeze",
        "Stars write better stories than we do",
        "Keep this feeling a little while longer",
        "Slow mornings and much longer looks",
        "A little chaos wrapped in a lot of magic",
        "Chasing light and catching feelings too",
        "Quiet nights with beautifully loud dreams",
        "She dreamed it first, then she did it",
        "Warm light for a very cool mood",
        "Float a little and worry a lot less",
        "The kind of calm you can't explain well",
        "Sunsets and secret smiles just for you",
        "Breathe it in and let the rest go",
        "Made of stardust and pure nerve",
        "Daydreams always taste better at dusk",
        "Soft as the last light of the day",
        "Wish you were here, almost anyway",
        "Take the slow way home tonight",
        "Moonlight simply suits me better always",
        "Dream just a little bit closer to me",
        "Hold on to this mood before it fades",
        "Lemonade skies and beautifully lazy eyes",
        "Whisper it gently to the night sky",
        "Let the whole world blur around us",
        "Home is a feeling and not a place",
    ],
}

CTAS = {
    "flirty": [
        "Follow for the next one",
        "Double tap if you looked twice",
        "Save this one for later",
        "Comment your favorite line",
    ],
    "bold": [
        "Follow to watch the journey",
        "Tag someone who needs this today",
        "Save it for a hard day",
        "Double tap if you agree",
    ],
    "dreamy": [
        "Follow for softer moments",
        "Save this mood for later",
        "Share this with your favorite person",
        "Tell me your favorite line",
    ],
}

HASHTAGS = {
    "flirty": ["#flirty", "#tease", "#glamour", "#instagood", "#modelsofinstagram",
               "#reels", "#explore", "#fyp", "#aigirl"],
    "bold": ["#confidence", "#boss", "#motivation", "#glamour", "#instagood",
             "#reels", "#explore", "#fyp", "#aigirl"],
    "dreamy": ["#dreamy", "#aesthetic", "#mood", "#sunset", "#instagood",
               "#reels", "#explore", "#fyp", "#aigirl"],
}

# Phrases an LLM loves to lean on — banned from both seeds and generations.
CLICHE = [
    "never give up", "trust the process", "live laugh love", "rise and grind",
    "boss babe", "sigma", "hustle harder", "good vibes only", "stay strong",
    "be yourself", "dream big", "work hard play harder", "level up",
    "she believed she could", "own your story", "embrace the grind",
    "be the change", "this too shall pass", "carpe diem", "yolo",
    "10 percent better", "no pain no gain", "chase your dreams",
    "make it happen", "believe in yourself",
]

MOODS = list(SEED.keys())
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF]+", flags=re.UNICODE)
_WORD = re.compile(r"[a-z0-9]+")


# ---------------------------------------------------------------------------
# normalisation + similarity
# ---------------------------------------------------------------------------
def normalise(text: str) -> str:
    t = (text or "").lower()
    for ch in "‘’'\"“”.,!?;:()[]{}-–—/\\|":
        t = t.replace(ch, " ")
    t = "".join(c for c in t if c in string.ascii_lowercase + string.digits + " \t\n")
    return " ".join(t.split())


def similar(a: str, b: str, threshold: float = 0.62) -> bool:
    """Jaccard similarity over word sets."""
    wa, wb = set(_WORD.findall(normalise(a))), set(_WORD.findall(normalise(b)))
    if not wa or not wb:
        return False
    inter = len(wa & wb)
    union = len(wa | wb)
    return (inter / union) >= threshold


def is_cliche(text: str) -> bool:
    n = normalise(text)
    return any(c.replace(" ", " ") in n or c in n for c in CLICHE)


def strip_emoji(text: str) -> str:
    return _EMOJI.sub("", text or "")


def accept_line(text: str, pool: List[str]) -> Optional[str]:
    """
    Hard filter for candidate lines. Returns the cleaned line or None.
    18-118 chars, Roman script only, no emoji/hashtags/mentions/clichés,
    not an exact or near-duplicate of anything in pool.
    """
    if not text:
        return None
    line = " ".join(strip_emoji(text).split())
    line = line.strip(" \"'“”‘’")
    if not (18 <= len(line) <= 118):
        return None
    if any(ord(c) > 0x24F for c in line):        # non-Latin script (e.g. Devanagari)
        return None
    if "#" in line or "@" in line or "http" in line.lower():
        return None
    if any(c in line for c in ("🔥", "💋", "😈")):
        return None
    if is_cliche(line):
        return None
    norm = normalise(line)
    if not norm or db.line_exists(norm):
        return None
    if any(similar(line, p) for p in pool):
        return None
    return line


def _recent_and_seed_pool(mood: str) -> List[str]:
    pool = list(SEED.get(mood, []))
    pool += [r["line"] for r in db.recent_lines(40)]
    return pool


# ---------------------------------------------------------------------------
# LLM (OpenAI-compatible chat completions — Gemini by default)
# ---------------------------------------------------------------------------
def chat_json(prompt: str, temperature: float = 0.95,
              timeout: int = 90) -> Optional[dict]:
    """Ask the LLM for JSON. Rotates through configured models on failure."""
    if not LLM_API_KEY:
        return None
    import requests

    def call(model: str):
        resp = requests.post(
            f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            },
            timeout=timeout,
        )
        if resp.status_code >= 400:
            raise net.HttpError(resp.status_code, resp.text[:500], resp.url)
        return resp.json()

    for model in LLM_MODELS:
        try:
            data = net.with_retry(
                lambda m=model: call(m), attempts=3, base_ms=1500,
                label=f"llm:{model}")
            content = data["choices"][0]["message"]["content"] or ""
            if data["choices"][0].get("finish_reason") == "length":
                print(f"[lines] {model}: truncated response, trying next model")
                continue
            obj = extract_json(content)
            if obj is not None:
                return obj
            print(f"[lines] {model}: no JSON in response")
        except Exception as e:  # noqa: BLE001 — model rotation
            print(f"[lines] {model} failed: {e}")
    return None


def extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:  # noqa: BLE001
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:  # noqa: BLE001
            return None
    return None


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------
def _cliche_block() -> str:
    return ", ".join(CLICHE[:12])


def expand(theme: str, mood: str, count: int = 12) -> int:
    """Generate new lines for the theme. Returns how many were kept."""
    existing = [r["line"] for r in db.recent_lines(30)]
    seed_sample = random.sample(SEED.get(mood, []),
                                min(8, len(SEED.get(mood, []))))
    prompt = (
        "Write {n} short Instagram reel overlay lines for a page about {niche}. "
        "Theme of this post: {theme}.\n"
        "RULES:\n"
        "- ENGLISH ONLY, one sentence each, 8 to 16 words, 18 to 118 characters.\n"
        "- Flirty, confident or dreamy tone. Suggestive is fine, but NEVER explicit: "
        "no sexual acts, no nudity, no body-part focus, no offers of anything.\n"
        "- No emoji, no hashtags, no quotes, no em dashes, no greeting or sign-off.\n"
        "- Banned clichés: {cliches}\n"
        "- Do NOT repeat or rephrase any of these existing lines: {existing}\n"
        "Return ONLY JSON: {{\"lines\": [\"...\", \"...\"]}}"
    ).format(
        n=count, niche=CONTENT_NICHE, theme=theme, cliches=_cliche_block(),
        existing=json.dumps(existing + seed_sample, ensure_ascii=False),
    )
    obj = chat_json(prompt, temperature=1.0)
    if not obj:
        return 0
    candidates = obj.get("lines") or []
    if not isinstance(candidates, list):
        return 0
    pool = _recent_and_seed_pool(mood)
    kept = 0
    for raw in candidates:
        if not isinstance(raw, str):
            continue
        line = accept_line(raw, pool)
        if not line:
            continue
        if db.insert_line(theme, line, normalise(line), engine="llm"):
            pool.append(line)
            kept += 1
    print(f"[lines] llm kept {kept}/{len(candidates)} lines for {theme}")
    return kept


def compose(theme: str, mood: str, allow_generate: bool = True) -> tuple:
    """Returns (line, engine). Never returns an empty line."""
    # 1. unused generated lines for this theme
    fresh = db.available_generated(theme, limit=5)
    if fresh:
        pick = random.choice(fresh)
        db.mark_line_used(pick["norm"])
        return pick["line"], "llm"

    # 2. generate a fresh batch
    if allow_generate:
        expand(theme, mood, count=12)
        fresh = db.available_generated(theme, limit=4)
        if fresh:
            pick = random.choice(fresh)
            db.mark_line_used(pick["norm"])
            return pick["line"], "llm"

    # 3. first unused seed for the mood
    seeds = SEED.get(mood) or SEED["flirty"]
    for s in seeds:
        if not db.is_asset_used("seed", f"{mood}::{normalise(s)}"):
            db.mark_asset("seed", f"{mood}::{normalise(s)}")
            return s, "seed"

    # 4. recycle the least-recently-used seed (never fails)
    oldest_key = None
    oldest_at = None
    for s in seeds:
        key = f"{mood}::{normalise(s)}"
        rows = [r for r in db.asset_usage("seed") if r["key"] == key]
        at = rows[0]["used_at"] if rows else ""
        if oldest_at is None or at < oldest_at:
            oldest_key, oldest_at = key, at
    if oldest_key:
        db.mark_asset("seed", oldest_key)
        idx = [f"{mood}::{normalise(s)}" for s in seeds].index(oldest_key)
        return seeds[idx], "recycled"
    return seeds[0], "seed"  # pragma: no cover — seed pools are never empty


# ---------------------------------------------------------------------------
# captions
# ---------------------------------------------------------------------------
def clean_hashtags(tags: List[str], limit: int = 12) -> List[str]:
    out, seen = [], set()
    for t in tags:
        t = (t or "").strip().lower()
        if not re.fullmatch(r"#[a-z0-9_]{2,28}", t):
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def fallback_hashtags(mood: str) -> List[str]:
    base = HASHTAGS.get(mood, HASHTAGS["flirty"])
    extra = ["#reels", "#explore", "#fyp", "#viral", "#aiart",
             "#model", "#trending", "#instaviral", "#beautiful"]
    return clean_hashtags(base + random.sample(extra, 4))


def build_caption(theme: str, mood: str, line: str,
                  credit: str = "") -> str:
    """line / hook / hashtags / music credit — hard-capped at 2200 chars."""
    hook, tags = None, None
    if LLM_API_KEY:
        prompt = (
            "Write the caption body and hashtags for an Instagram reel. "
            "The overlay quote on the video is: \"{line}\". "
            "Niche: {niche}. Theme: {theme}. "
            "RULES: caption body under 140 characters, flirty/confident tone, "
            "must NOT repeat the quote, at most one call-to-action, at most one "
            "emoji. Hashtags: exactly 9, mix of broad and niche, lowercase, "
            "no banned-tag spam. "
            "Return ONLY JSON: {{\"hook\": \"...\", \"hashtags\": "
            "[\"#tag\", \"...\"]}}"
        ).format(line=line, niche=CONTENT_NICHE, theme=theme)
        obj = chat_json(prompt, temperature=0.9)
        if obj:
            h = obj.get("hook")
            if isinstance(h, str) and 0 < len(h.strip()) <= 200:
                hook = " ".join(strip_emoji(h).split())
            t = obj.get("hashtags")
            if isinstance(t, list):
                tags = clean_hashtags([x for x in t if isinstance(x, str)])

    if not hook:
        hook = random.choice(CTAS.get(mood, CTAS["flirty"]))
    if not tags:
        tags = fallback_hashtags(mood)

    parts = [line, hook, " ".join(tags)]
    if credit:
        parts.append(credit)
    caption = "\n\n".join(p for p in parts if p)
    caption = re.sub(r"\n{3,}", "\n\n", caption)
    return caption[:2200]


def first_line(caption: str) -> str:
    for ln in (caption or "").splitlines():
        if ln.strip():
            return normalise(ln)
    return ""


def bank_status() -> dict:
    return {m: len(SEED.get(m, [])) for m in MOODS}
