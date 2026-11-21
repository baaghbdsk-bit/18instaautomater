"""
manage.py — local diagnostics and maintenance CLI.

  python manage.py doctor     # check ffmpeg/libass, fonts, DB, keys, library
  python manage.py status     # recent posts, today's count, last publish
  python manage.py library    # photo/music/line inventory + usage
  python manage.py insights   # engagement per theme
  python manage.py cleanup    # prune temp files + checkpoint the DB
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

import db
import lines
from config import (
    ACCOUNTS,
    BASE_DIR,
    DAILY_CAP_PER_ACCOUNT,
    DURATION_MAX,
    DURATION_MIN,
    FFMPEG_BIN,
    FFPROBE_BIN,
    FONT_QUOTE,
    LLM_API_KEY,
    LLM_BASE_URL,
    MIN_GAP_MINUTES,
    PERCHANCE_URL,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from validate import faststart, probe

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = YELLOW = RESET = ""


def _ok(msg):   print(f"  {GREEN}OK{RESET}   {msg}")
def _bad(msg):  print(f"  {RED}FAIL{RESET} {msg}")
def _warn(msg): print(f"  {YELLOW}WARN{RESET} {msg}")


def doctor() -> int:
    failures = 0
    print("doctor\n")

    # ffmpeg / ffprobe / filters
    import shutil
    import subprocess
    if shutil.which(FFMPEG_BIN) or Path(FFMPEG_BIN).exists():
        try:
            out = subprocess.run([FFMPEG_BIN, "-version"], capture_output=True,
                                 text=True, timeout=30)
            _ok(f"ffmpeg: {out.stdout.splitlines()[0][:70]}")
        except Exception as e:  # noqa: BLE001
            _bad(f"ffmpeg not runnable: {e}"); failures += 1
    else:
        _bad(f"ffmpeg not found at {FFMPEG_BIN}"); failures += 1

    if shutil.which(FFPROBE_BIN) or Path(FFPROBE_BIN).exists():
        _ok(f"ffprobe: {FFPROBE_BIN}")
    else:
        _bad(f"ffprobe not found at {FFPROBE_BIN}"); failures += 1

    try:
        out = subprocess.run([FFMPEG_BIN, "-hide_banner", "-filters"],
                             capture_output=True, text=True, timeout=30)
        txt = out.stdout + out.stderr
        for f in ("ass", "zoompan", "loudnorm", "drawtext", "vignette"):
            if f" {f} " in txt or f" {f}\n" in txt or f"\n .. {f}" in txt:
                _ok(f"filter: {f}")
            else:
                _bad(f"filter missing: {f} (install a full ffmpeg build)"); failures += 1
    except Exception as e:  # noqa: BLE001
        _bad(f"could not list filters: {e}"); failures += 1

    # fonts
    fonts = list((BASE_DIR / "assets" / "fonts").glob("*.ttf"))
    if FONT_QUOTE.exists():
        _ok(f"quote font: {FONT_QUOTE.name}")
    else:
        _bad(f"quote font missing: {FONT_QUOTE}"); failures += 1
    _ok(f"{len(fonts)} fonts in assets/fonts")

    # DB
    try:
        db.checkpoint()
        _ok(f"database: {db.DB_PATH.name} ({db.line_count()} generated lines)")
    except Exception as e:  # noqa: BLE001
        _bad(f"database: {e}"); failures += 1

    # accounts
    usable = [a for a in ACCOUNTS if a["username"] and a["password"]]
    if usable:
        for a in usable:
            has_sess = (BASE_DIR / "sessions" / f"{a['username']}.json").exists()
            _ok(f"account {a['name']} ({a['username']}) "
                f"{'session cached' if has_sess else 'no session yet'}")
    else:
        _bad("no IG accounts configured (IG_USERNAME_1/IG_PASSWORD_1)"); failures += 1

    # curated quote bank (quotes NEVER come from an LLM)
    try:
        import quote_bank
        bank = quote_bank.load_bank()
        if bank:
            _ok(f"quote bank: {len(bank)} approved lines "
                f"({quote_bank.bank_fingerprint(bank)[:12]}...)")
        else:
            _bad("quote bank empty — add approved lines to "
                 "assets/quotes/approved.json"); failures += 1
    except Exception as e:  # noqa: BLE001
        _bad(f"quote bank: {e}"); failures += 1

    # LLM (optional: caption hooks/hashtags only, never quote generation)
    if LLM_API_KEY:
        _ok(f"LLM configured: {LLM_BASE_URL} ({len(lines.LLM_MODELS)} models)")
    else:
        _warn("LLM_API_KEY empty — captions use fixed CTAs/hashtags; "
              "quotes come from the approved bank")

    # configured image provider
    try:
        from image_providers.registry import get_provider
        provider = get_provider()
        _ok(f"image provider: {provider.name}")
    except Exception as e:  # noqa: BLE001
        _bad(f"image provider: {e}"); failures += 1

    # Perchance
    try:
        import requests
        r = requests.get(f"{PERCHANCE_URL}/v1/health", timeout=4)
        _ok(f"Perchance API healthy ({r.status_code})") if r.status_code == 200 \
            else (_warn(f"Perchance unhealthy: HTTP {r.status_code}"))
    except Exception:
        _warn(f"Perchance not running at {PERCHANCE_URL} "
              "(CI starts it; locally run the wrapper)")

    # library
    n_music = len(list((BASE_DIR / "assets" / "music").glob("*/*")))
    n_images = len(list((BASE_DIR / "assets" / "images").glob("*.jpg")))
    if n_music:
        _ok(f"music: {n_music} tracks")
    else:
        _warn("music: empty (reels will be silent)")
    _ok(f"images on hand: {n_images}")

    # schedule
    _ok(f"cadence: {'unlimited' if not DAILY_CAP_PER_ACCOUNT else str(DAILY_CAP_PER_ACCOUNT) + '/day/account'}, "
        f"min gap {MIN_GAP_MINUTES} min, duration {DURATION_MIN}-{DURATION_MAX}s, "
        f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}")

    # existing output sample (newest by mtime)
    outs = sorted((BASE_DIR / "assets" / "output").glob("*.mp4"),
                  key=lambda p: p.stat().st_mtime)
    if outs:
        try:
            good, reasons, info = _validate(outs[-1])
            if good:
                _ok(f"latest render valid: {outs[-1].name} "
                    f"({info['duration']}s, faststart)")
            else:
                _warn(f"latest render has issues: {reasons}")
        except Exception as e:  # noqa: BLE001
            _warn(f"could not validate {outs[-1].name}: {e}")

    print()
    if failures:
        print(f"{RED}{failures} blocking issue(s).{RESET}")
        return 1
    print(f"{GREEN}All checks passed.{RESET}")
    return 0


def _validate(path):
    from validate import validate_video
    return validate_video(path)


def status() -> int:
    posts = db.recent_posts(20)
    today = sum(1 for p in posts
                if p["status"] == "published"
                and (p.get("published_at") or p["created_at"])[:10]
                == datetime.now().strftime("%Y-%m-%d"))
    last = db.last_published_at()
    print(f"posts in db : {db.recent_posts(1000).__len__()}")
    print(f"published   : {today} today "
          f"({'no cap' if not DAILY_CAP_PER_ACCOUNT else 'cap ' + str(DAILY_CAP_PER_ACCOUNT)})")
    print(f"last publish: {last or 'never'}")
    print(f"lines       : {db.line_count()} generated")
    print("\nrecent:")
    for p in posts[:10]:
        when = (p.get("published_at") or p["created_at"])[:16]
        print(f"  #{p['id']:<4} {when}  {p['status']:<10} "
              f"{(p.get('theme') or '-'):<18} {(p.get('title') or '')[:44]}")
    return 0


def library() -> int:
    print("music pools:")
    for pool in sorted(d.name for d in (BASE_DIR / "assets" / "music").iterdir()
                       if d.is_dir()):
        n = len(list((BASE_DIR / "assets" / "music" / pool).glob("*.mp3")))
        used = len([u for u in db.asset_usage("track")
                    if u["key"].startswith(f"assets/music/{pool}/")])
        print(f"  {pool:<10} {n} tracks ({used} used)")
    print("\nthemes:")
    for t, meta in __import__("themes").THEMES.items():
        print(f"  {t:<20} mood={meta['mood']:<8} music={meta['music']:<8} "
              f"prompts={len(meta['prompts'])}")
    print("\nseed lines:", lines.bank_status())
    print("prompt usage:", len(db.asset_usage("prompt")), "recorded")
    return 0


def insights() -> int:
    perf = db.theme_performance()
    if not perf:
        print("no engagement data yet (collected after your first posts age)")
        return 0
    med = sorted(perf.values())[len(perf) // 2] or 1
    for t, v in sorted(perf.items(), key=lambda kv: -kv[1]):
        print(f"  {t:<20} median engagement {v:>6.1f}  "
              f"({v / med:.1f}x baseline)")
    return 0


def cleanup() -> int:
    from pipeline import cleanup_temp
    before = sum(1 for _ in (BASE_DIR / "assets" / "tmp").rglob("*"))
    cleanup_temp(hours=0)
    after = sum(1 for _ in (BASE_DIR / "assets" / "tmp").rglob("*"))
    db.prune_assets("prompt", keep_last=300)
    db.checkpoint()
    print(f"temp files: {before} -> {after}; database checkpointed")
    return 0


def quotes() -> int:
    """Inspect the curated quote bank and usage without touching the network."""
    import quote_bank
    bank = quote_bank.load_bank()
    used = db.used_quote_ids()
    print(quote_bank.format_bank_status(bank, used))
    print(f"fingerprint: {quote_bank.bank_fingerprint(bank)}")
    return 0


def preview() -> int:
    """Build a prompt + compose a sample image with a local photo. Never publishes."""
    import random
    import quote_bank
    from character.profile import MASTER_PROFILE
    from character.variations import select_variation, build_prompt
    from compose_image import compose_quote_image
    from validate import validate_final_image

    bank = quote_bank.load_bank()
    quote = quote_bank.select_unused(bank, db.used_quote_ids())
    if quote is None:
        print("[!] Quote bank exhausted — nothing to preview.")
        return 1
    images = sorted((BASE_DIR / "assets" / "images").glob("*.jpg"))
    if not images:
        print("[!] No source image in assets/images. Generate one first.")
        return 1
    variation = select_variation([], rng=random.Random(0))
    prompt = build_prompt(MASTER_PROFILE, variation)
    print("=== PROMPT ===")
    print(prompt)
    print("\n=== QUOTE ===")
    print(quote.text)
    result = compose_quote_image(images[-1], quote.text, variant="lower")
    if not result.get("ok"):
        print(f"[!] Composition failed: {result.get('error')}")
        return 1
    ok, reasons, info = validate_final_image(
        result["path"], must_contain_quote=quote.text)
    print(f"\n=== PREVIEW ===\n{result['path']}")
    print(f"valid={ok} reasons={reasons} info={info}")
    return 0 if ok else 1


def generate() -> int:
    """Generate one real image through the configured provider (no composing)."""
    import quote_bank
    from character.profile import MASTER_PROFILE
    from character.variations import select_variation, build_prompt
    from image_providers.base import ImageRequest
    from image_providers.registry import get_provider
    from pipeline import _character_seed

    bank = quote_bank.load_bank()
    quote = quote_bank.select_unused(bank, db.used_quote_ids())
    variation = select_variation([])
    provider = get_provider()
    req = ImageRequest(
        prompt=build_prompt(MASTER_PROFILE, variation),
        negative_prompt=MASTER_PROFILE.negative_prompt_text(),
        seed=str(_character_seed()), model=MASTER_PROFILE.style_preset,
        metadata={"quote_id": quote.id, "variation": variation.key})
    print(f"[*] provider={provider.name} variation={variation.key}")
    result = provider.generate(req)
    print(f"ok={result.ok} status={result.status} path={result.path} "
          f"error={result.error}")
    return 0 if result.ok else 1


def session() -> int:
    """Show cached-session metadata only (never session contents)."""
    from post_instagram import session_status
    for acc in ACCOUNTS:
        if acc.get("username"):
            info = session_status(acc)
            print(f"{acc['name']}: cached={info['cached']} "
                  f"size={info['size']} path={info['path']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="quote-engine maintenance CLI")
    parser.add_argument("command", choices=["doctor", "status", "library",
                                            "insights", "cleanup",
                                             "quotes", "preview", "generate",
                                             "session"])
    args = parser.parse_args()
    return {"doctor": doctor, "status": status, "library": library,
            "insights": insights, "cleanup": cleanup, "quotes": quotes, "preview": preview,
             "generate": generate, "session": session}[args.command]()


if __name__ == "__main__":
    sys.exit(main())
