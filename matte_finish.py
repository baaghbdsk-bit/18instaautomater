"""
matte_finish.py — flatten specular highlights so skin reads dry and matte.

Perchance still paints bright streaks on skin even with strong negative
prompts. This deterministic pass compresses only the bright end of the curve
(specular highlights) and adds fine grain, without changing the character.
"""

from pathlib import Path

from PIL import Image

from config import IMAGES_DIR

HIGHLIGHT_START = 168
HIGHLIGHT_STRENGTH = 0.55   # 1.0 = no change, 0.0 = hard clip
GRAIN_LEVEL = 4             # +- pixel values


def _curve(value: int) -> int:
    if value <= HIGHLIGHT_START:
        return value
    return int(HIGHLIGHT_START +
               (value - HIGHLIGHT_START) * HIGHLIGHT_STRENGTH)


def apply_matte_finish(source) -> Path:
    src = Path(source)
    img = Image.open(src).convert("RGB")
    lut = [_curve(i) for i in range(256)]
    img = img.point(lut * 3)

    # Fine grain breaks up the smooth "plastic" look.
    import random
    rng = random.Random(20261122)
    px = img.load()
    w, h = img.size
    for _ in range(min(w * h, 90000)):
        x = rng.randrange(w)
        y = rng.randrange(h)
        r, g, b = px[x, y]
        delta = rng.randint(-GRAIN_LEVEL, GRAIN_LEVEL)
        px[x, y] = (max(0, min(255, r + delta)),
                    max(0, min(255, g + delta)),
                    max(0, min(255, b + delta)))

    out = IMAGES_DIR / f"matte_{src.stem}.jpg"
    img.save(out, quality=95)
    return out
