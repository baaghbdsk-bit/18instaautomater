"""
main.py
-------
Orchestrator for 18instaautomater.

Each run:
  1. Logs into both Instagram accounts (sessions reused automatically)
  2. Loops up to MAX_POSTS_PER_RUN times:
       - Picks a random photo + random music + random spicy line
       - Renders an MP4 via ffmpeg (feed 4:5 or story 9:16, alternating)
       - Posts to the next account in rotation
       - Sleeps a random interval between posts

Edit config.py to set your accounts, schedule, and text lines.

Setup:
  pip install -r requirements.txt
  cp .env.example .env   # then fill in your credentials
  # Drop photos into assets/images/, music into assets/music/
  python main.py
"""

import random
import time
from pathlib import Path

from config import (
    ACCOUNTS,
    IMAGES_DIR,
    MUSIC_DIR,
    OUTPUT_DIR,
    POST_INTERVAL_MIN,
    POST_INTERVAL_MAX,
    MAX_POSTS_PER_RUN,
    RANDOM_SEED,
)
from generate_video import make_video
from lines import SEED, build_caption
from post_instagram import login_account, post_feed, post_story, logout_all

# Every seed line across moods (legacy flat list).
SPICY_LINES = [ln for pool in SEED.values() for ln in pool]


def _random_file(folder: Path, exps=(".jpg", ".jpeg", ".png", ".webp")) -> Path | None:
    """Pick a random image file from a folder, or None if empty."""
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exps]
    return random.choice(files) if files else None


def _random_music() -> Path | None:
    """Pick a random music file from assets/music (any mood), or None."""
    exps = (".mp3", ".wav", ".m4a", ".aac")
    files = [p for p in MUSIC_DIR.rglob("*")
             if p.is_file() and p.suffix.lower() in exps]
    return random.choice(files) if files else None


def _pick_spicy_line() -> str:
    return random.choice(SPICY_LINES) if SPICY_LINES else ""


def _build_caption(line: str) -> str:
    """Caption text for feed posts (uses the shared caption builder)."""
    mood = random.choice(list(SEED.keys()))
    return build_caption("manual", mood, line)


def main():
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)

    missing = [a for a in ACCOUNTS if not a["username"] or not a["password"]]
    if missing:
        print("[!] Fill in IG_USERNAME_1/IG_PASSWORD_1 etc. in .env first.")
        return

    if not any(IMAGES_DIR.iterdir()):
        print(f"[!] No images found in {IMAGES_DIR}. "
              f"Drop some photos there first, then re-run.")
        return

    clients = {}
    for acc in ACCOUNTS:
        try:
            clients[acc["name"]] = login_account(acc)
        except Exception as e:
            print(f"[!] Could not log into {acc['name']}: {e}")

    if not clients:
        print("[!] No accounts logged in. Exiting.")
        return

    account_names = list(clients.keys())
    acct_idx = 0
    mode_idx = 0
    cycle_i = 0
    posts_done = 0
    attempts = 0
    try:
        while posts_done < MAX_POSTS_PER_RUN:
            acct_name = account_names[acct_idx % len(account_names)]
            mode = "feed" if mode_idx % 2 == 0 else "story"
            cl = clients[acct_name]

            image = _random_file(IMAGES_DIR)
            if image is None:
                print("[!] No usable image files in assets/images. Stopping.")
                break
            music = _random_music()

            line = _pick_spicy_line()

            stamp = time.strftime("%Y%m%d_%H%M%S")
            out_name = f"{acct_name}_{mode}_{stamp}.mp4"

            print(f"\n=== Post {posts_done + 1}/{MAX_POSTS_PER_RUN} ===")
            print(f"Account : {acct_name}")
            print(f"Type    : {mode}")
            print(f"Image   : {image.name if image else 'NONE'}")
            print(f"Music   : {music.name if music else 'NONE'}")
            print(f"Line    : {line}")

            try:
                video_path = make_video(image, music, line, mode=mode, output_name=out_name)
                print(f"[+] Rendered {video_path}")
            except Exception as e:
                print(f"[!] Render failed: {e}")
                attempts += 1
                acct_idx += 1
                mode_idx += 1
                if attempts >= MAX_POSTS_PER_RUN * 2:
                    print("[!] Too many consecutive failures. Stopping.")
                    break
                if posts_done + attempts < MAX_POSTS_PER_RUN:
                    sleep_for = random.randint(POST_INTERVAL_MIN, POST_INTERVAL_MAX)
                    print(f"    sleeping {sleep_for}s before next attempt...")
                    time.sleep(sleep_for)
                continue

            caption = _build_caption(line)
            ok = False
            if mode == "feed":
                ok = post_feed(cl, video_path, caption=caption)
            else:
                ok = post_story(cl, video_path)

            if ok:
                print(f"[+] Successfully posted to {acct_name} ({mode})")
            else:
                print(f"[!] Post to {acct_name} ({mode}) failed")

            acct_idx += 1
            mode_idx += 1
            posts_done += 1
            attempts = 0

            if posts_done < MAX_POSTS_PER_RUN:
                sleep_for = random.randint(POST_INTERVAL_MIN, POST_INTERVAL_MAX)
                mins = sleep_for // 60
                secs = sleep_for % 60
                print(f"    sleeping {mins}m {secs}s before next post...")
                time.sleep(sleep_for)

    finally:
        logout_all(clients)

    print(f"\nDone. Posted {posts_done} video(s).")


if __name__ == "__main__":
    main()