"""
gen_sample_nvidia.py
--------------------
Generates a real AI image via NVIDIA NIM (Stable Diffusion XL) using your API key,
then renders it into feed + story videos through the existing ffmpeg pipeline.

Usage:
  python gen_sample_nvidia.py

The API key is read from the env var NVIDIA_API_KEY (set it before running) —
it is never printed to the console.
"""

import os
import sys
import json
import base64
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# NVIDIA NIM API config
# ---------------------------------------------------------------------------
API_KEY = os.getenv("NVIDIA_API_KEY", "")
if not API_KEY:
    print("[!] Set NVIDIA_API_KEY env var first, e.g.:")
    print('    $env:NVIDIA_API_KEY="nvapi-..."')
    sys.exit(1)

# Correct NVIDIA NIM Flux.1-schnell endpoint (per krueng.ai docs)
FLUX_URL = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# Suggestive but SAFE prompt — no nudity/sex acts so Instagram won't flag it.
PROMPT = (
    "beautiful woman, elegant evening dress, soft romantic lighting, "
    "cinematic portrait, shallow depth of field, warm tones, "
    "highly detailed, 8k, fashion photography, moody atmosphere"
)

# Flux.1-schnell required params: cfg_scale=0, steps=4, mode="base"
FLUX_PAYLOAD = {
    "prompt": PROMPT,
    "mode": "base",
    "cfg_scale": 0,
    "width": 1024,
    "height": 1024,
    "seed": 0,
    "steps": 4,
}

OUTPUT_IMG = Path("assets/images/nvidia_sample.jpg")
OUTPUT_IMG.parent.mkdir(parents=True, exist_ok=True)


def generate_image() -> bool:
    print(f"[*] Calling NVIDIA NIM Flux.1-schnell...")
    print(f"    Prompt: {PROMPT[:80]}...")
    try:
        resp = requests.post(FLUX_URL, headers=HEADERS, json=FLUX_PAYLOAD, timeout=300)
    except requests.RequestException as e:
        print(f"[!] Request failed: {e}")
        return False

    print(f"    HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(f"[!] API error: {resp.text[:500]}")
        return False

    data = resp.json()

    # Response: {"artifacts":[{"base64":"..."}]}
    artifacts = data.get("artifacts", [])
    if not artifacts:
        print(f"[!] No artifacts in response: {json.dumps(data)[:300]}")
        return False

    b64 = artifacts[0].get("base64")
    if not b64:
        print(f"[!] No base64 in artifact: {json.dumps(data)[:300]}")
        return False

    img_bytes = base64.b64decode(b64)
    OUTPUT_IMG.write_bytes(img_bytes)
    print(f"[+] Image saved: {OUTPUT_IMG} ({len(img_bytes)/1024:.1f} KB)")
    return True


def main():
    if not generate_image():
        sys.exit(1)

    # Render through the existing ffmpeg pipeline (feed + story)
    from generate_video import make_video

    print("\n--- Rendering FEED (4:5) ---")
    feed_out = make_video(
        str(OUTPUT_IMG), None,
        "Cant look away... \u26a1\ufe0f",
        mode="feed",
        output_name="nvidia_feed.mp4",
    )
    print(f"[+] Feed video: {feed_out}")
    print(f"    Size: {Path(feed_out).stat().st_size / 1024:.1f} KB")

    print("\n--- Rendering STORY (9:16) ---")
    story_out = make_video(
        str(OUTPUT_IMG), None,
        "Dreaming of you tonight \ud83c\udf19",
        mode="story",
        output_name="nvidia_story.mp4",
    )
    print(f"[+] Story video: {story_out}")
    print(f"    Size: {Path(story_out).stat().st_size / 1024:.1f} KB")

    print("\n=== READY TO POST ===")
    print(f"Image : {OUTPUT_IMG}")
    print(f"Feed  : {feed_out}")
    print(f"Story : {story_out}")
    print("\nDrop more AI photos into assets/images/ and run: python main.py")


if __name__ == "__main__":
    main()