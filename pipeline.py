"""
pipeline.py — one autonomous reel run (CI entry point).

Order of operations mirrors the reference engine's run.js, so a duplicated
cron, a delayed runner, or a crash mid-publish can never double-post:

  1. kill switch
  2. auth preflight (login every usable account)
  3. crash reconciliation (stale 'publishing' rows resolved against live posts)
  4. cadence guards (daily cap, minimum gap)
  5. engagement-refreshed theme pick
  6. build: line -> image -> music -> render -> validate -> caption
  7. duplicate-caption check, then publish with safe retry
  8. record + notify + cleanup

Usage:
  python pipeline.py                 # full run
  python pipeline.py --dry-run       # build only, never publish
  python pipeline.py --skip-generate # reuse newest image in assets/images
  python pipeline.py --strict        # fail instead of posting a placeholder
  python pipeline.py --theme beach_golden --slot manual
"""

import argparse
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows consoles default to cp1252 and crash on emoji.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

import db
import generate_ai_image
import lines as lines_mod
import notify
from config import (
    ACCOUNTS,
    BASE_DIR,
    DAILY_CAP_PER_ACCOUNT,
    DRY_RUN,
    KILL_SWITCH,
    MIN_GAP_MINUTES,
    MUSIC_CREDIT,
    RANDOM_SEED,
    TMP_DIR,
)
from generate_video import render_reel
from post_instagram import (
    find_duplicate,
    login_account,
    logout_all,
    media_info,
    recent_media,
    upload_reel,
)
from themes import THEME_KEYS, theme_meta
from validate import validate_video

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".aac")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def newest_image() -> Path | None:
    files = [p for p in generate_ai_image.IMAGES_DIR.iterdir()
             if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def music_pool_files(pool: str) -> list:
    d = BASE_DIR / "assets" / "music" / pool
    if not d.exists():
        return []
    return sorted(p for p in d.iterdir()
                  if p.is_file() and p.suffix.lower() in MUSIC_EXTS)


def pick_track(theme: str) -> Path | None:
    """LRU pick inside the theme's music pool; falls back to every pool."""
    pool = theme_meta(theme)["music"]
    candidates = music_pool_files(pool) or [
        p for p in (BASE_DIR / "assets" / "music").glob("*/*")
        if p.suffix.lower() in MUSIC_EXTS]
    if not candidates:
        return None
    keys = [str(p.relative_to(BASE_DIR)) for p in candidates]
    chosen = db.pick_asset("track", keys)
    if chosen is None:
        return None
    db.mark_asset("track", chosen)
    return BASE_DIR / chosen


def choose_theme(force: str | None) -> str:
    """Weighted by measured engagement, anti-repeat, random factor."""
    if force:
        return force
    medians = db.theme_performance()
    baseline_vals = sorted(v for v in medians.values() if v > 0)
    baseline = baseline_vals[len(baseline_vals) // 2] if baseline_vals else 0

    recent = db.recent_posts(10)
    last_theme = recent[0]["theme"] if recent else None
    recent_themes = {p["theme"] for p in recent}

    best, best_score = None, -1.0
    for t in THEME_KEYS:
        weight = 1.0
        if baseline:
            weight = min(max(medians.get(t, baseline) / baseline, 0.45), 2.4)
        if t == last_theme:
            weight *= 0.1
        elif t in recent_themes:
            weight *= 0.5
        score = weight * (0.55 + random.random() * 0.9)
        if score > best_score:
            best, best_score = t, score
    return best or random.choice(THEME_KEYS)


def pick_account(clients: dict) -> dict | None:
    """Rotation that skips capped accounts instead of halting the run."""
    usable = [a for a in ACCOUNTS if a["username"] and a["password"]
              and a["name"] in clients]
    if not usable:
        return None
    try:
        start_i = int(db.get_state("rotation_index", "0") or "0")
    except ValueError:
        start_i = 0
    for off in range(len(usable)):
        acct = usable[(start_i + off) % len(usable)]
        if db.count_published_today(acct["name"]) < DAILY_CAP_PER_ACCOUNT:
            db.set_state("rotation_index", str(start_i + off + 1))
            return acct
    return None


def collect_insights(clients: dict, limit: int = 8,
                     min_age_hours: float = 6) -> int:
    """Refresh likes/comments on recent posts (fail-soft). Returns count."""
    updated = 0
    now = datetime.now()
    targets = [p for p in db.recent_posts(40)
               if p.get("status") == "published" and p.get("ig_id")]
    for post in targets[:limit]:
        fresh = db.insight_for(post["ig_id"])
        if fresh:
            try:
                age = now - datetime.fromisoformat(fresh["collected_at"])
                if age.total_seconds() < min_age_hours * 3600:
                    continue
            except ValueError:
                pass
        cl = clients.get(post.get("account"))
        if not cl:
            continue
        info = media_info(cl, post["ig_id"])
        if info:
            db.upsert_insight(post["ig_id"], post.get("account") or "",
                              info["likes"], info["comments"],
                              post_id=post["id"])
            updated += 1
    return updated


def reconcile_stale(clients: dict) -> int:
    """Resolve rows stuck in 'publishing' against the live account."""
    stale = db.stale_publishing(min_age_minutes=5)
    if not stale:
        return 0

    live_cache: dict = {}
    recovered = 0

    for post in stale:
        acct_name = post.get("account")
        cl = clients.get(acct_name)
        acct = next((a for a in ACCOUNTS if a["name"] == acct_name), None)
        if not cl or not acct:
            continue
        if acct_name not in live_cache:
            live_cache[acct_name] = recent_media(cl, acct["username"], amount=25)
        live = live_cache[acct_name]
        if live is None:
            # Fetch failed (network) — defer, never guess.
            print(f"[reconcile] post {post['id']}: profile unreadable, deferring")
            continue
        target = lines_mod.first_line(post.get("caption_text") or "")
        match = next((m for m in live
                      if target and len(target) >= 8
                      and lines_mod.first_line(m["caption"]) == target), None)
        if match:
            db.update_post(
                post["id"], status="published", ig_id=match["pk"],
                permalink=(f"https://www.instagram.com/p/{match['code']}/"
                           if match.get("code") else None),
                published_at=post.get("published_at")
                or datetime.now().isoformat(timespec="seconds"))
            recovered += 1
            print(f"[reconcile] post {post['id']} found live -> published")
        else:
            db.update_post(post["id"], status="failed",
                           error="not found on profile during reconciliation")
            print(f"[reconcile] post {post['id']} not live -> failed")
    return recovered


def cleanup_temp(hours: float = 24.0) -> None:
    if not TMP_DIR.exists():
        return
    cutoff = time.time() - hours * 3600
    for p in TMP_DIR.rglob("*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def report(status: str, post_id, theme, line, info, notes) -> None:
    def row(k, v):
        return f"| {k} | {v} |"

    rows = ["| field | value |", "|---|---|",
            row("status", status),
            row("post", post_id or "-"),
            row("theme", theme or "-"),
            row("line", str(line or "-").replace("|", "/")),
            row("video", (info or {}).get("path", "-")),
            row("duration", (info or {}).get("duration", "-"))]
    for n in notes:
        rows.append(row("note", n))
    notify.summary("\n".join(rows))
    notify.set_output("status", status)
    notify.set_output("post_id", str(post_id or ""))
    if status == "failed" and notes:
        notify.webhook(f"❌ reel-engine run failed: {notes[-1]}")


# ---------------------------------------------------------------------------
# main run
# ---------------------------------------------------------------------------
def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate + render + post one reel")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate + render only, never publish")
    parser.add_argument("--skip-generate", action="store_true",
                        help="Reuse the newest image in assets/images")
    parser.add_argument("--strict", action="store_true",
                        help="Fail (exit 2) instead of posting a placeholder")
    parser.add_argument("--theme", choices=THEME_KEYS, default=None,
                        help="Force a content theme")
    parser.add_argument("--slot", default="cron",
                        help="Run label stored in the runs table")
    parser.add_argument("--force", action="store_true",
                        help="Publish even if cadence guards would skip")
    args = parser.parse_args(argv)

    if RANDOM_SEED:
        random.seed(int(RANDOM_SEED))

    dry = args.dry_run or DRY_RUN
    run_id = db.start_run(args.slot)
    clients: dict = {}
    post_id = None
    notes: list = []
    outcome = {"status": "failed", "theme": None, "line": None, "info": None}

    def finish(status_: str, error: str | None = None) -> None:
        db.finish_run(run_id, status_, post_id=post_id, error=error)

    try:
        # 1. kill switch
        if KILL_SWITCH or (BASE_DIR / "data" / "KILL_SWITCH").exists():
            print("[=] Kill switch on — skipping.")
            outcome["status"] = "skipped"
            finish("skipped")
            return 0

        # 2. auth preflight
        usable = [a for a in ACCOUNTS if a["username"] and a["password"]]
        if not usable and not dry:
            raise RuntimeError("no accounts configured (set IG_USERNAME_1 etc.)")
        errors: list = []
        for acct in usable:
            try:
                clients[acct["name"]] = login_account(acct)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{acct['name']}: {e}")
        if usable and not clients:
            raise RuntimeError("login failed for every account — " +
                               "; ".join(errors))
        if errors:
            notes.append("accounts unavailable: " + "; ".join(errors))

        # 3. crash reconciliation
        recovered = reconcile_stale(clients)
        if recovered:
            notes.append(f"reconciled {recovered} stale post(s)")

        # 4. cadence guards
        if not dry and not args.force:
            gap = db.minutes_since_last_publish()
            if gap < MIN_GAP_MINUTES:
                print(f"[=] Min gap not reached ({gap:.0f} < "
                      f"{MIN_GAP_MINUTES} min). Skipping.")
                outcome["status"] = "skipped"
                finish("skipped", "min-gap")
                return 0

        account = pick_account(clients)
        if not account and not dry:
            print("[=] Daily cap reached on every account. Skipping.")
            outcome["status"] = "skipped"
            finish("skipped", "daily-cap")
            return 0
        account = account or (usable[0] if usable else
                              {"name": "dry-run", "username": "(none)",
                               "handle": "@xene.ai"})
        used_today = db.count_published_today(account["name"])
        print(f"[*] Account : {account['name']} ({account['username']})")
        print(f"[*] Today   : {used_today}/{DAILY_CAP_PER_ACCOUNT} published")

        # 5. engagement refresh (fail-soft)
        try:
            n = collect_insights(clients)
            if n:
                notes.append(f"insights refreshed for {n} post(s)")
        except Exception as e:  # noqa: BLE001
            print(f"[insights] refresh failed (non-fatal): {e}")

        # 6a. theme + line
        theme = choose_theme(args.theme)
        meta = theme_meta(theme)
        mood, music_pool_name = meta["mood"], meta["music"]
        print(f"[*] Theme   : {theme} (mood={mood}, music={music_pool_name})")
        line, engine = lines_mod.compose(theme, mood)
        print(f"[*] Line    : {line}  [{engine}]")
        outcome.update(theme=theme, line=line)

        post_id = db.insert_post(account=account["name"], theme=theme,
                                 title=line, engine=engine, status="building")

        # 6b. image
        if args.skip_generate:
            image, source = newest_image(), "existing"
            if image is None:
                raise RuntimeError("--skip-generate set but no images found")
        else:
            image, source = generate_ai_image.generate(theme=theme)
        if args.strict and source == "placeholder":
            db.update_post(post_id, status="failed",
                           error="strict: placeholder image")
            raise RuntimeError("STRICT: image generation fell back to "
                               "placeholder — refusing to build")

        # 6c. music
        track = pick_track(theme)

        # 6d. render
        info = render_reel(
            image, track, line, mode="story",
            variant=random.choice(["upper", "center", "lower"]),
            output_name=f"reel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        outcome["info"] = info
        db.update_post(post_id, video_path=info["path"], image_path=str(image),
                       image_source=source, music_path=info["music"],
                       variant=info["variant"], duration_sec=info["duration"])

        # 6e. validate
        ok, reasons, vinfo = validate_video(info["path"])
        if not ok:
            raise RuntimeError("video validation failed: " + ", ".join(reasons))
        print(f"[+] Valid reel: {vinfo['duration']}s, "
              f"{vinfo['bytes'] / 1e6:.1f} MB")

        # 6f. caption
        credit = MUSIC_CREDIT if track else ""
        caption = lines_mod.build_caption(theme, mood, line, credit=credit)
        db.update_post(post_id, caption_text=caption, status="built")

        if dry:
            print("[=] Dry run: not publishing.")
            print(caption)
            outcome["status"] = "dry-run"
            finish("dry-run")
            return 0

        # 7a. duplicate guard
        cl = clients[account["name"]]
        dup = find_duplicate(cl, account["username"], caption, lookback=12)
        if dup:
            db.update_post(post_id, status="skipped",
                           error=f"duplicate caption already live (pk={dup})")
            print("[=] Identical opening line already live — skipping.")
            outcome["status"] = "skipped"
            finish("skipped", "duplicate-caption")
            return 0

        # 7b. publish — row is written to 'publishing' BEFORE the upload
        db.update_post(post_id, status="publishing")
        res = upload_reel(cl, account["username"], info["path"], caption)
        if res["ok"]:
            permalink = (f"https://www.instagram.com/p/{res['code']}/"
                         if res.get("code") else None)
            db.update_post(post_id, status="published", ig_id=res.get("pk"),
                           permalink=permalink,
                           published_at=datetime.now().isoformat(
                               timespec="seconds"))
            if res.get("recovered"):
                notes.append("upload confirmed live after retry check")
            print(f"[+] Published: {permalink or res.get('pk')}")
            outcome["status"] = "published"
            finish("published")
            return 0

        db.update_post(post_id, status="failed", error=res["error"])
        raise RuntimeError(f"upload failed: {res['error']}")

    except Exception as e:  # noqa: BLE001 — top-level failure reporting
        msg = str(e)[:800]
        notify.error(msg)
        notes.append(msg)
        outcome["status"] = "failed"
        finish("failed", msg)
        if args.strict and "placeholder" in msg:
            return 2
        return 1
    finally:
        if clients:
            logout_all(clients)
        report(outcome["status"], post_id, outcome["theme"], outcome["line"],
               outcome["info"], notes)
        cleanup_temp()
        db.checkpoint()


if __name__ == "__main__":
    sys.exit(run())
