"""
themes.py — content themes for the glamour/AI-model niche (port of themes.js).

Each theme drives three things:
  * prompts  — Perchance image prompt templates for this scene/mood
  * mood     — which flirty-line pool the caption quote comes from
  * music    — which music pool the background track comes from

Add a theme here and the weighted selector picks it up automatically.
"""

import random

# line pools live in lines.py:   flirty | bold | dreamy
# music pools live in assets/music/:  energy | dark | chill

THEMES = {
    "night_neon": {
        "mood": "flirty",
        "music": "dark",
        "queries": ["neon night portrait", "city night glamour"],
        "prompts": [
            "cinematic night portrait of a stunning woman standing on a rain-slick "
            "city street, teal and magenta neon glow reflecting off wet asphalt, "
            "bokeh storefront lights behind her, confident sultry gaze at camera, "
            "fitted black outfit, soft rim light, shallow depth of field, "
            "shot on 85mm, ultra detailed, 9:16 vertical",
            "glamorous woman leaning against a neon-lit wall at night, purple and "
            "blue neon signs, smoke in the air, moody cinematic lighting, "
            "fashion editorial look, direct eye contact, 9:16 vertical",
            "beautiful woman lit by a single neon sign in a dark alley, "
            "cyberpunk color grade, teal shadows and pink highlights, "
            "cinematic still, ultra detailed face, 9:16 vertical",
        ],
    },
    "beach_golden": {
        "mood": "dreamy",
        "music": "chill",
        "queries": ["golden hour beach", "sunset shore portrait"],
        "prompts": [
            "breathtaking golden hour portrait of a beautiful woman on a tropical "
            "beach, sun setting behind her creating a warm rim light, ocean waves "
            "blurred in background, flowy summer dress, wind in hair, "
            "dreamy lens flare, cinematic color grade, 9:16 vertical",
            "woman walking along the shoreline at sunset, wet sand reflections, "
            "golden sunlight, candid laugh, summer vibe, film photography look, "
            "shallow depth of field, 9:16 vertical",
            "sun-kissed portrait of a gorgeous woman under a beach umbrella, "
            "sparkling turquoise water behind, straw hat, warm tones, "
            "editorial travel photography, 9:16 vertical",
        ],
    },
    "fitness": {
        "mood": "bold",
        "music": "energy",
        "queries": ["fitness portrait", "gym aesthetic"],
        "prompts": [
            "athletic beautiful woman in a modern gym, dramatic overhead lighting, "
            "confident pose, stylish workout gear, sweat glow on skin, "
            "dark moody gym background with bokeh lights, cinematic, "
            "9:16 vertical",
            "fit woman stretching on a rooftop at sunrise, city skyline behind, "
            "warm morning light, sporty fashion, powerful confident expression, "
            "cinematic photography, 9:16 vertical",
            "portrait of a stunning fitness influencer after workout, gym mirror "
            "selfie aesthetic, ring light reflection, toned and confident, "
            "editorial style, 9:16 vertical",
        ],
    },
    "fashion_editorial": {
        "mood": "bold",
        "music": "energy",
        "queries": ["high fashion portrait", "editorial studio glamour"],
        "prompts": [
            "high fashion editorial portrait of a stunning woman, seamless "
            "studio backdrop in deep burgundy, dramatic studio lighting, "
            "designer outfit, fierce confident expression, Vogue magazine "
            "quality, 9:16 vertical",
            "glamorous woman in a sequin evening dress on a marble staircase, "
            "chandelier light, luxury interior, cinematic still, "
            "elegant and sultry, 9:16 vertical",
            "fashion week street style portrait of a beautiful woman, stylish "
            "coat and sunglasses, blurred city crowd behind, natural light, "
            "editorial photography, 9:16 vertical",
        ],
    },
    "mirror_selfie": {
        "mood": "flirty",
        "music": "chill",
        "queries": ["mirror selfie aesthetic", "casual glamour portrait"],
        "prompts": [
            "trendy mirror selfie of a beautiful woman in a stylish outfit, "
            "cozy apartment with warm fairy lights, phone covering part of her "
            "face, playful expression, casual influencer aesthetic, "
            "natural window light, 9:16 vertical",
            "woman taking a mirror selfie in a glam dressing room, vanity bulbs "
            "glowing, stylish outfit, confident smile, warm tones, "
            "social media aesthetic, 9:16 vertical",
            "aesthetic bathroom mirror selfie, moody lighting, trendy streetwear, "
            "plant and tiles in background, candid vibe, 9:16 vertical",
        ],
    },
    "cozy_bedroom": {
        "mood": "dreamy",
        "music": "chill",
        "queries": ["cozy morning portrait", "soft bedroom light"],
        "prompts": [
            "cozy morning portrait of a beautiful woman in an oversized knit "
            "sweater on a soft bed, warm sunlight through sheer curtains, "
            "soft blankets, gentle sleepy smile, dreamy soft focus, "
            "lifestyle photography, 9:16 vertical",
            "woman with a cup of coffee by a rainy window, cozy indoor lighting, "
            "comfortable sweater, warm intimate mood, cinematic still, "
            "9:16 vertical",
            "beautiful woman lounging on a couch with a book, golden hour light "
            "spilling across the room, plants and candles, relaxed candid mood, "
            "9:16 vertical",
        ],
    },
    "office_chic": {
        "mood": "bold",
        "music": "energy",
        "queries": ["boss lady portrait", "office fashion glamour"],
        "prompts": [
            "confident beautiful woman in a tailored blazer, modern office "
            "penthouse with city view behind glass, powerful boss-lady energy, "
            "dramatic window light, fashion editorial, 9:16 vertical",
            "glamorous business woman walking through a marble lobby, "
            "elegant suit, motion blur crowd behind, cinematic lighting, "
            "9:16 vertical",
            "portrait of a stunning woman at a stylish desk, laptop and coffee, "
            "soft desk lamp glow, smart casual fashion, focused expression, "
            "9:16 vertical",
        ],
    },
    "rooftop_luxury": {
        "mood": "flirty",
        "music": "energy",
        "queries": ["rooftop pool luxury", "skyline glamour evening"],
        "prompts": [
            "beautiful woman at a rooftop infinity pool at dusk, city skyline "
            "behind, string lights, elegant summer dress, drink in hand, "
            "luxury travel aesthetic, cinematic warm tones, 9:16 vertical",
            "glamorous woman by a luxury hotel pool at sunset, turquoise water, "
            "palm trees, sun loungers, confident relaxed pose, "
            "resort editorial photography, 9:16 vertical",
            "champagne moment on a rooftop terrace, beautiful woman laughing, "
            "bokeh city lights behind, evening glamour, 9:16 vertical",
        ],
    },
    "street_style": {
        "mood": "bold",
        "music": "energy",
        "queries": ["streetwear portrait", "urban fashion night"],
        "prompts": [
            "street style portrait of a beautiful woman in oversized streetwear, "
            "graffiti wall background, golden afternoon light, confident stance, "
            "urban fashion editorial, 9:16 vertical",
            "stylish woman crossing a busy city street at night, motion-blurred "
            "traffic lights, neon reflections, cinematic street photography, "
            "9:16 vertical",
            "cool portrait of a gorgeous woman on subway steps, natural light "
            "from above, trendy outfit, candid urban vibe, 9:16 vertical",
        ],
    },
    "rain_moody": {
        "mood": "dreamy",
        "music": "dark",
        "queries": ["rainy day portrait", "moody window light woman"],
        "prompts": [
            "moody portrait of a beautiful woman under a clear umbrella in the "
            "rain, city lights blurred behind, wet hair, cinematic blue tones, "
            "melancholic beauty, 9:16 vertical",
            "woman standing by a rain-streaked window, soft grey daylight on her "
            "face, thoughtful expression, film photography look, "
            "intimate quiet mood, 9:16 vertical",
            "beautiful woman in a trench coat walking through evening rain, "
            "street lamp glow, reflections on wet pavement, cinematic, "
            "9:16 vertical",
        ],
    },
    "summer_festival": {
        "mood": "flirty",
        "music": "energy",
        "queries": ["summer festival portrait", "sunshine happy glamour"],
        "prompts": [
            "beautiful woman at an outdoor summer festival, fairy lights and "
            "colorful flags, golden sunset light, flower crown, joyful laugh, "
            "carefree vibe, cinematic, 9:16 vertical",
            "sun-kissed woman dancing at a street party, colorful confetti in "
            "the air, bright daylight, motion energy, festival fashion, "
            "9:16 vertical",
            "glamorous portrait at a beach bonfire night, warm firelight on her "
            "face, friends bokeh behind, summer night mood, 9:16 vertical",
        ],
    },
    "winter_cozy": {
        "mood": "dreamy",
        "music": "chill",
        "queries": ["winter portrait knitwear", "snow day glamour"],
        "prompts": [
            "cozy winter portrait of a beautiful woman in an oversized scarf and "
            "knit beanie, soft snowfall, rosy cheeks, warm smile, cold blue "
            "tones with warm skin, cinematic, 9:16 vertical",
            "woman holding a warm drink at a winter cafe window, steam rising, "
            "soft fairy lights, intimate warm mood, film look, 9:16 vertical",
            "glamorous woman in a fur-look coat on a snowy city street at dusk, "
            "street lights glowing, elegant winter fashion, 9:16 vertical",
        ],
    },
}

THEME_KEYS = list(THEMES.keys())
MUSIC_POOLS = ["energy", "dark", "chill"]
LINE_MOODS = ["flirty", "bold", "dreamy"]
VISUAL_VARIANTS = ["upper", "center", "lower"]


def theme_meta(theme: str) -> dict:
    if theme in THEMES:
        return dict(THEMES[theme], theme=theme)
    fallback = "night_neon"
    print(f"[themes] unknown theme {theme!r}, falling back to {fallback}")
    return dict(THEMES[fallback], theme=fallback)


def pick_prompt(theme: str, used: set | None = None) -> str:
    """Pick a not-recently-used prompt template for the theme."""
    meta = theme_meta(theme)
    templates = meta["prompts"]
    unused = [t for t in templates if not used or t not in used]
    pool = unused or templates
    return random.choice(pool)
