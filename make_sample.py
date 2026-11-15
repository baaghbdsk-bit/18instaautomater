"""
make_sample.py
--------------
Creates a sample placeholder image + tests the full video generation pipeline.
Replace assets/images/sample.jpg with your real AI-generated photos later.
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Create a sample image (gradient + overlay text)
# ---------------------------------------------------------------------------
img = Image.new("RGB", (1080, 1350))

# Draw a gradient background (dark pink/purple vibe)
for y in range(1350):
    r = int(20 + (y / 1350) * 40)
    g = int(10 + (y / 1350) * 20)
    b = int(30 + (y / 1350) * 50)
    for x in range(1080):
        img.putpixel((x, y), (r, g, b))

draw = ImageDraw.Draw(img)

# Try to load a font, fall back to default
font_path = "C:/Windows/Fonts/arial.ttf"
try:
    font_big = ImageFont.truetype(font_path, 70)
    font_small = ImageFont.truetype(font_path, 40)
except Exception:
    font_big = ImageFont.load_default()
    font_small = ImageFont.load_default()

# Sample "spicy" text on the image itself
draw.text((1080 // 2, 600), "SAMPLE PHOTO", fill=(255, 255, 255),
          font=font_big, anchor="mm")
draw.text((1080 // 2, 700), "Replace with your AI image", fill=(200, 200, 200),
          font=font_small, anchor="mm")

img.save("assets/images/sample.jpg", quality=90)
print("[+] Sample image created: assets/images/sample.jpg")

# ---------------------------------------------------------------------------
# 2. Test the full video generation pipeline (feed + story)
# ---------------------------------------------------------------------------
from generate_video import make_video

print("\n--- Testing FEED (4:5) ---")
feed_out = make_video(
    "assets/images/sample.jpg",
    None,
    "Cant look away... \u26a1\ufe0f",
    mode="feed",
    output_name="sample_feed.mp4"
)
print(f"[+] Feed video: {feed_out}")
print(f"    Size: {Path(feed_out).stat().st_size / 1024:.1f} KB")

print("\n--- Testing STORY (9:16) ---")
story_out = make_video(
    "assets/images/sample.jpg",
    None,
    "Dreaming of you tonight \ud83c\udf19",
    mode="story",
    output_name="sample_story.mp4"
)
print(f"[+] Story video: {story_out}")
print(f"    Size: {Path(story_out).stat().st_size / 1024:.1f} KB")

print("\n=== PIPELINE TEST PASSED ===")
print("Both feed and story videos rendered successfully.")
print("You can now drop your real AI photos into assets/images/ and run: python main.py")