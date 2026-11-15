"""
make_test_post.py
-----------------
Generates a realistic-looking test image locally + renders feed & story videos.
Shows you exactly what your posts will look like before you connect Instagram.

No API key needed — everything runs locally with Pillow + ffmpeg.
"""

from PIL import Image, ImageDraw, ImageFilter, ImageFont
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Generate a realistic-looking AI-style test image locally
# ---------------------------------------------------------------------------
def make_test_image(path: str | Path):
    """Create a photo-like image: gradient background, figure silhouette,
    soft lighting, and depth — looks like an AI-generated portrait."""
    W, H = 1024, 1024
    img = Image.new("RGB", (W, H), (15, 10, 20))
    draw = ImageDraw.Draw(img)

    # --- Gradient background (deep purple to warm pink) ---
    for y in range(H):
        t = y / H
        r = int(20 + t * 40)
        g = int(10 + t * 30)
        b = int(25 + t * 60)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # --- Soft glow / bokeh circles ---
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for _ in range(25):
        x = random.randint(-100, W + 100)
        y = random.randint(-100, H + 100)
        rad = random.randint(60, 220)
        color = (255, 120, 180, random.randint(10, 40))
        gdraw.ellipse([x - rad, y - rad, x + rad, y + rad], fill=color)
    glow = glow.filter(ImageFilter.GaussianBlur(60))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(img)

    # --- Central figure silhouette (dress shape) ---
    cx = W // 2
    # Torso
    draw.ellipse([cx - 110, H // 2 - 60, cx + 110, H // 2 + 120], fill=(30, 25, 35))
    # Dress skirt
    draw.polygon([
        (cx - 140, H // 2 + 120),
        (cx + 140, H // 2 + 120),
        (cx + 110, H - 40),
        (cx - 110, H - 40),
    ], fill=(35, 28, 40))
    # Head / hair
    draw.ellipse([cx - 60, H // 2 - 180, cx + 60, H // 2 - 60], fill=(15, 12, 18))
    # Shoulder highlight
    draw.ellipse([cx - 90, H // 2 - 40, cx - 40, H // 2 + 10], fill=(60, 45, 55))
    draw.ellipse([cx + 40, H // 2 - 40, cx + 90, H // 2 + 10], fill=(60, 45, 55))

    # --- Rim light on figure ---
    rim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rdraw = ImageDraw.Draw(rim)
    rdraw.ellipse([cx - 130, H // 2 - 80, cx + 130, H // 2 + 140], outline=(255, 160, 120, 60), width=6)
    rim = rim.filter(ImageFilter.GaussianBlur(15))
    img = Image.alpha_composite(img.convert("RGBA"), rim).convert("RGB")
    draw = ImageDraw.Draw(img)

    # --- Vignette ---
    vignette = Image.new("L", (W, H), 0)
    vdraw = ImageDraw.Draw(vignette)
    vdraw.ellipse([-W * 0.2, -H * 0.2, W * 1.2, H * 1.2], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(200))
    vignette = Image.eval(vignette, lambda px: 255 - px)
    vignette_rgb = Image.merge("RGB", (vignette,) * 3)
    img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0)
    img = Image.composite(img, Image.eval(vignette_rgb, lambda px: int(px * 0.4)), vignette)

    img.save(path, quality=92)
    print(f"[+] Test image created: {path} ({Path(path).stat().st_size / 1024:.1f} KB)")


# ---------------------------------------------------------------------------
# 2. Render feed + story videos through the existing pipeline
# ---------------------------------------------------------------------------
def render_videos(image_path: str | Path):
    from generate_video import make_video

    print("\n--- Rendering FEED (1080x1350, 4:5, 30s) ---")
    feed_out = make_video(
        image_path,
        None,
        "Cant look away... \u26a1\ufe0f",
        mode="feed",
        output_name="test_feed_post.mp4",
    )
    print(f"[+] Feed video: {feed_out}")
    print(f"    Size: {Path(feed_out).stat().st_size / 1024:.1f} KB")

    print("\n--- Rendering STORY (1080x1920, 9:16, 30s) ---")
    story_out = make_video(
        image_path,
        None,
        "Dreaming of you tonight \ud83c\udf19",
        mode="story",
        output_name="test_story_post.mp4",
    )
    print(f"[+] Story video: {story_out}")
    print(f"    Size: {Path(story_out).stat().st_size / 1024:.1f} KB")

    return feed_out, story_out


def main():
    img_path = Path("assets/images/test_post.jpg")
    img_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print("  GENERATING TEST POST IMAGE + VIDEOS")
    print("=" * 50)

    make_test_image(img_path)
    render_videos(img_path)

    print("\n" + "=" * 50)
    print("  TEST POSTS READY")
    print("=" * 50)
    print("Feed : assets/output/test_feed_post.mp4")
    print("Story: assets/output/test_story_post.mp4")
    print("\nOpen those MP4 files to see exactly what your posts will look like.")


if __name__ == "__main__":
    main()