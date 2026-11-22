"""
pipeline.py — one autonomous glamour quote-IMAGE run (CI entry point).

This is the single orchestration point for the product workflow:

   1. kill switch
   2. auth preflight (session/cookie based, via instagrapi)
   3. crash reconciliation (stale rows resolved against live posts)
   4. cadence guards (daily cap, minimum gap)
   5. claim one UNUSED line from the curated quote bank (never an LLM filler)
   6. build the prompt: fixed master character identity + curated variation
   7. generate the actual image through the configured provider adapter
   8. validate the downloaded image (placeholder/real check)
   9. compose the quote onto the image -> Instagram-ready static image
  10. validate the final image
  11. record the full lifecycle in SQLite
  12. duplicate-caption check, then publish with safe retry (unless dry-run)

The default output is a Reel made from the composed quote image with a trending
Instagram catalog track. ``--mode photo`` publishes the static image instead;
``--mode legacy-reel`` keeps the original video/theme flow for compatibility.

Usage:
    python pipeline.py                       # full image-post run
    python pipeline.py --dry-run             # build only, never publish
    python pipeline.py --strict              # never accept a placeholder
    python pipeline.py --mode photo          # static quote image instead
    python pipeline.py --mode legacy-reel    # original video/theme flow
    python pipeline.py --variation upper     # force text placement
"""

import argparse
import json
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
import notify
from config import (
    ACCOUNTS,
    IG_ACTIVE_ACCOUNT,
    ALLOW_PLACEHOLDER,
    BASE_DIR,
    CHARACTER_ID,
    COMPOSE_VARIANTS,
    DAILY_CAP_PER_ACCOUNT,
    DRY_RUN,
    FINAL_IMAGES_DIR,
    IMAGES_DIR,
    KILL_SWITCH,
    MIN_GAP_MINUTES,
    MUSIC_CREDIT,
    MUSIC_CREDIT_IN_CAPTION,
    MUSIC_ENABLED,
    OUTPUT_DIR,
    PERCHANCE_ASPECT,
    PERCHANCE_GUIDANCE,
    PERCHANCE_NEGATIVE,
    PERCHANCE_STYLE,
    QUOTE_LOW_WATERMARK,
    RANDOM_SEED,
    TMP_DIR,
)
from audio_mux import mux_track_audio
from curated_audio import pick_curated_track
from local_music import pick_local_track
from matte_finish import apply_matte_finish
from music_match import track_from_metadata, pick_orgavsm_track
from post_instagram import (
    find_duplicate,
    login_account,
    logout_all,
    media_info,
    recent_media,
    upload_photo_post,
    upload_reel,
    upload_reel_with_music,
)
from themes import THEME_KEYS, theme_meta
from validate import validate_video

# New product modules (created in this implementation).
import quote_bank
from character.consistency import build_consistency, consistency_metadata
from character.profile import MASTER_PROFILE
from character.variations import get_variation, select_variation, build_prompt, variation_keys
from compose_image import compose_quote_image, is_placeholder_image
from image_providers.base import ImageRequest
from image_providers.registry import get_provider
from generate_video import still_video
from validate import validate_final_image

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".aac")


# ---------------------------------------------------------------------------
# helpers retained from the original engine (kept for backward compatibility)
# ---------------------------------------------------------------------------
def newest_image() -> Path | None:
    files = [p for p in IMAGES_DIR.iterdir()
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
        if (not DAILY_CAP_PER_ACCOUNT or
                db.count_published_today(acct["name"]) < DAILY_CAP_PER_ACCOUNT):
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
        # One process may only hold the current account's client; any
        # authenticated client can read another account's public media.
        cl = clients.get(post.get("account")) or next(iter(clients.values()), None)
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
    """Resolve rows stuck in a non-terminal state against the live account."""
    getter = getattr(db, "recent_posts_need_recovery", None)
    stale = getter() if getter else db.stale_publishing(min_age_minutes=5)
    if not stale:
        return 0

    from lines import first_line

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
            print(f"[reconcile] post {post['id']}: profile unreadable, deferring")
            continue
        target = first_line(post.get("caption_text") or "")
        match = next((m for m in live
                      if target and len(target) >= 8
                      and first_line(m["caption"]) == target), None)
        if match:
            db.update_post(
                post["id"], status="published", ig_id=match["pk"],
                permalink=(f"https://www.instagram.com/p/{match['code']}/"
                           if match.get("code") else None),
                published_at=post.get("published_at")
                or datetime.now().isoformat(timespec="seconds"))
            recovered += 1
            print(f"[reconcile] post {post['id']} found live -> published")
        elif post.get("status") == "publishing":
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
            row("output", (info or {}).get("path", "-"))]
    for n in notes:
        rows.append(row("note", n))
    notify.summary("\n".join(rows))
    notify.set_output("status", status)
    notify.set_output("post_id", str(post_id or ""))
    if status == "failed" and notes:
        notify.webhook(f"quote-engine run failed: {notes[-1]}")


# ---------------------------------------------------------------------------
# image-post workflow
# ---------------------------------------------------------------------------
def _select_quote(post_id: int):
    """Claim one unused approved line atomically. Never invents a line."""
    bank = quote_bank.load_bank()
    used = db.used_quote_ids() if hasattr(db, "used_quote_ids") else set()
    if quote_bank.is_low(bank, used, watermark=QUOTE_LOW_WATERMARK):
        notify.warn(
            f"quote bank running low: {quote_bank.unused_count(bank, used)} unused")
    quote = quote_bank.select_unused(bank, used)
    if quote is None:
        raise RuntimeError(
            "curated quote bank exhausted — add approved lines to "
            "assets/quotes/approved.json (no LLM filler will be used)")
    claim = getattr(db, "claim_quote", None)
    if claim and not claim(quote.id, post_id):
        # Another worker claimed it between selection and insert — retry once.
        used = db.used_quote_ids()
        quote = quote_bank.select_unused(bank, used)
        if quote is None or not claim(quote.id, post_id):
            raise RuntimeError("could not atomically claim an unused quote")
    return quote, bank


def _build_generation_request(quote, variation, seed, consent=True):
    """Fixed identity first, curated variation second, honest metadata."""
    prompt = build_prompt(MASTER_PROFILE, variation)
    consistency = build_consistency(
        MASTER_PROFILE,
        seed=seed,
        reference_images=MASTER_PROFILE.reference_images or None,
    )
    return ImageRequest(
        prompt=prompt,
        negative_prompt=MASTER_PROFILE.negative_prompt_text(),
        aspect_ratio=PERCHANCE_ASPECT,
        width=1080,
        height=1920,
        seed=str(seed) if seed is not None else None,
        model=MASTER_PROFILE.style_preset,
        num_images=1,
        reference_images=consistency.reference_images,
        metadata={
            "character_id": CHARACTER_ID,
            "variation": variation.key,
            "quote_id": quote.id,
            **consistency_metadata(consistency, MASTER_PROFILE),
        },
    )


def _character_seed() -> int:
    """Stable per-character seed for reproducibility (NOT an identity lock)."""
    key = f"character_seed:{CHARACTER_ID}"
    raw = db.get_state(key)
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    seed = random.randint(0, 2**31 - 1)
    db.set_state(key, str(seed))
    return seed


def run_image(args) -> int:
    """Static quote-image workflow. Returns process exit code."""
    dry = args.dry_run or DRY_RUN
    run_id = db.start_run(args.slot)
    clients: dict = {}
    post_id = None
    local_track = None
    notes: list = []
    outcome = {"status": "failed", "theme": "image-post", "line": None,
               "info": None}

    def finish(status_: str, error: str | None = None) -> None:
        db.finish_run(run_id, status_, post_id=post_id, error=error)

    try:
        # 1. kill switch
        if KILL_SWITCH or (BASE_DIR / "data" / "KILL_SWITCH").exists():
            print("[=] Kill switch on — skipping.")
            outcome["status"] = "skipped"
            finish("skipped")
            return 0

        # 2. auth preflight (session/cookie based)
        usable = [a for a in ACCOUNTS if a["username"] and a["password"]
                  and (not IG_ACTIVE_ACCOUNT or a["name"] == IG_ACTIVE_ACCOUNT)]
        if not usable and not dry:
            raise RuntimeError("no accounts configured (set IG_USERNAME_1 etc.)")
        errors: list = []
        for acct in usable:
            try:
                clients[acct["name"]] = login_account(acct)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{acct['name']}: {e}")
        if usable and not clients and not dry:
            raise RuntimeError("login failed for every account — " +
                               "; ".join(errors))
        if errors:
            notes.append("accounts unavailable: " + "; ".join(errors))

        # 3. crash reconciliation
        recovered = reconcile_stale(clients)
        if recovered:
            notes.append(f"reconciled {recovered} stale post(s)")

        # 4. cadence guards (minimum-gap guard removed by owner request)
        account = pick_account(clients)
        if not account and not dry:
            print("[=] Daily cap reached on every account. Skipping.")
            outcome["status"] = "skipped"
            finish("skipped", "daily-cap")
            return 0
        account = account or (usable[0] if usable else
                              {"name": "dry-run", "username": "(none)",
                               "handle": ""})
        print(f"[*] Account : {account['name']} ({account['username']})")

        # Burst guard: no second publish for the same account inside the
        # configured gap (default 150 min), even across separate runs.
        if (MIN_GAP_MINUTES and not dry and
                db.minutes_since_last_publish(account["name"]) < MIN_GAP_MINUTES):
            age = db.minutes_since_last_publish(account["name"])
            print(f"[=] {account['name']}: last publish {age:.1f} min ago "
                  f"(min gap {MIN_GAP_MINUTES}) — skipping")
            outcome["status"] = "skipped"
            finish("skipped", "min-gap")
            return 0

        # 5. claim one unused approved line
        post_id = db.insert_post(
            account=account["name"], theme="image-post", title="",
            engine="quote-bank", status="pending")
        quote, _bank = _select_quote(post_id)
        db.update_post(post_id, title=quote.text, quote_id=quote.id,
                       quote_text=quote.text, status="quote_selected")
        outcome["line"] = quote.text
        print(f"[*] Quote   : {quote.text}  [{quote.id}]")

        # 6. prompt = fixed identity + curated variation
        used_variations = [r["key"] for r in db.asset_usage("variation")]
        variation = (get_variation(args.variation) if args.variation else
                     select_variation(used_variations))
        db.mark_asset("variation", variation.key)
        request = _build_generation_request(quote, variation, _character_seed())
        print(f"[*] Variation: {variation.key} / character {CHARACTER_ID}")
        print(f"[*] Prompt  : {request.prompt[:180]}...")
        db.update_post(
            post_id, status="image_generating",
            prompt_text=request.prompt,
            prompt_metadata=json.dumps(request.metadata, ensure_ascii=False),
            provider=request.metadata.get("provider", "config"),
            model=request.model, seed=request.seed)

        # 7. image generation through the provider adapter
        if args.skip_generate:
            raw_path = newest_image()
            if raw_path is None:
                raise RuntimeError("--skip-generate set but no images found")
            source = "existing"
        else:
            provider = get_provider()
            print(f"[*] Provider: {provider.name}")
            result = provider.generate(request)
            if not result.ok:
                raise RuntimeError(f"image generation failed: {result.error}")
            raw_path = Path(result.path)
            source = provider.name
            db.update_post(post_id, attempts=result.metadata.get("attempts", 0),
                           error_stage=None)
        print(f"[*] Raw image: {raw_path}")

        # 7b. Deterministic matte finish: compress specular highlights and add
        # fine grain so the skin reads dry, not oily/plastic.
        if source != "placeholder":
            raw_path = apply_matte_finish(raw_path)
            print(f"[*] Matte image: {raw_path}")

        # 8. reject placeholders (never publish them as real AI images)
        if is_placeholder_image(raw_path) or source == "placeholder":
            if args.strict or not ALLOW_PLACEHOLDER:
                raise RuntimeError(
                    "refusing to publish a placeholder image; image generation "
                    "must succeed or the run must fail")
            notes.append("WARNING: placeholder image used (dev mode only)")

        # 9. compose the quote onto the image
        variant = args.variation if args.variation in COMPOSE_VARIANTS else "lower"
        composed = compose_quote_image(
            raw_path, quote.text, output_path=None, variant=variant,
            handle=account.get("handle", ""))
        if not composed.get("ok"):
            raise RuntimeError(f"composition failed: {composed.get('error')}")
        final_path = Path(composed["path"])
        db.update_post(
            post_id, generation_status="downloaded", generation_path=str(raw_path),
            image_path=str(raw_path), image_source=source,
            composition_status="complete", final_image_path=str(final_path),
            video_path=str(final_path), status="composition_complete")

        # 10. validate the final image
        ok, reasons, vinfo = validate_final_image(
            final_path, must_contain_quote=quote.text)
        if not ok:
            raise RuntimeError("final image validation failed: " +
                               ", ".join(reasons))
        vw, vh = vinfo.get("size", (1080, 1920))
        print(f"[+] Valid image: {vw}x{vh}, "
              f"{vinfo['bytes']/1e6:.1f} MB")

        # 10b. turn the composed image into a Reel (default output mode)
        publish_path = final_path
        if args.mode == "reel":
            reel_path = OUTPUT_DIR / (
                f"reel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
            # Local bank first: no catalog API, no rate limits, and the audio
            # is physically muxed into the MP4 so it is always audible.
            local_track = None
            if MUSIC_ENABLED:
                # Priority: owner files > curated real songs > stock CC-BY bed.
                local_track = pick_local_track(custom_only=True)
                if not local_track:
                    client = clients.get(account["name"])
                    if client is not None:
                        local_track = pick_curated_track(client)
                if not local_track:
                    local_track = pick_local_track()
            if local_track:
                print(f"[*] Music: {local_track['title']} "
                      f"({local_track['pool']})")
            reel = still_video(
                raw_path, reel_path,
                silent_audio=False,
                music_path=(local_track or {}).get("path"),
                quote_text=quote.text,
                variant=variant,
                handle=account.get("handle", ""))
            vok, vreasons, vinfo2 = validate_video(
                reel["path"], require_audio=True)
            if not vok:
                raise RuntimeError("reel validation failed: " +
                                   ", ".join(vreasons))
            publish_path = Path(reel["path"])
            print(f"[+] Valid reel: {vinfo2['duration']}s, "
                  f"{vinfo2['bytes'] / 1e6:.1f} MB")
            outcome["info"] = {"path": str(publish_path),
                               "image": str(final_path), **vinfo2}
            db.update_post(post_id, output_kind="reel",
                           video_path=str(publish_path),
                           duration_sec=reel["duration"])
        else:
            outcome["info"] = {"path": str(final_path), **vinfo}
        db.update_post(post_id, status="ready_to_publish")

        # 11. caption (music credit is not applicable to static image posts)
        from lines import build_caption
        credit = ""
        if local_track and MUSIC_CREDIT_IN_CAPTION:
            credit = local_track["credit"]
        caption = build_caption("image-post", quote.mood or "flirty",
                                quote.text, credit=credit)
        db.update_post(post_id, caption_text=caption)

        if dry:
            print(f"[=] Dry run: not publishing. Output: {publish_path}")
            print(caption)
            outcome["status"] = "dry-run"
            finish("dry-run")
            return 0

        # 12a. duplicate guard
        cl = clients[account["name"]]
        dup = find_duplicate(cl, account["username"], caption, lookback=12)
        if dup:
            db.update_post(post_id, status="skipped",
                           error=f"duplicate caption already live (pk={dup})")
            outcome["status"] = "skipped"
            finish("skipped", "duplicate-caption")
            return 0

        # 12b. Instagram catalog music is only a fallback when the local
        # bank is empty. Local audio is already muxed into the MP4 above.
        track = None
        if local_track:
            try:
                meta = json.loads((db.get_post(post_id) or {}).get(
                    "prompt_metadata") or "{}")
            except (ValueError, TypeError):
                meta = {}
            meta["music"] = {
                "track_id": local_track.get("track_id") or Path(local_track["path"]).name,
                "title": local_track["title"],
                "artist": (local_track.get("artist") or local_track["pool"]),
                "source": local_track.get("source", "local_bank"),
                "credit": local_track["credit"],
            }
            db.update_post(post_id, prompt_metadata=json.dumps(
                meta, ensure_ascii=False))
        elif MUSIC_ENABLED:
            used_music = [r["key"] for r in db.asset_usage("music")]
            track, track_id = pick_orgavsm_track(
                cl, used_keys=used_music,
                mood=getattr(variation, "mood", None))
            if track_id:
                db.mark_asset("music", track_id)
            if track is not None:
                try:
                    meta = json.loads((db.get_post(post_id) or {}).get(
                        "prompt_metadata") or "{}")
                except (ValueError, TypeError):
                    meta = {}
                meta["music"] = {
                    "track_id": track_id,
                    "title": getattr(track, "title", ""),
                    "artist": getattr(track, "display_artist", ""),
                    "source": "instagram_catalog",
                }
                db.update_post(post_id, prompt_metadata=json.dumps(
                    meta, ensure_ascii=False))
                print(f"[*] Music : {meta['music']['title']} — "
                      f"{meta['music']['artist']}")
            else:
                notes.append("trending music unavailable — posting without audio")

        # 12b-2. Mux the same catalog audio into the MP4 so playback is
        # audible even when the client does not apply the catalog metadata.
        # Mux is FATAL: a silent MP4 must never be uploaded.
        if track is not None and args.mode == "reel":
            muxed = mux_track_audio(publish_path, track,
                                    float(reel["duration"]))
            candidate = Path(muxed["path"])
            vok2, vreasons2, _ = validate_video(candidate)
            if not vok2:
                raise RuntimeError("muxed reel invalid: " +
                                   ", ".join(vreasons2))
            publish_path = candidate
            db.update_post(post_id, video_path=str(publish_path))
            print(f"[+] Reel audio muxed from "
                  f"{(meta.get('music') or {}).get('title', 'catalog track')}")

        # 12c. publish — pass a real JPG thumbnail (not the composed PNG).
        thumb_path = final_path
        if not thumb_path.suffix.lower() in (".jpg", ".jpeg"):
            thumb_path = Path(str(thumb_path) + ".jpg")
        db.update_post(post_id, status="publishing")
        if args.mode == "reel":
            res = upload_reel_with_music(cl, account["username"], publish_path,
                                         caption, track=track,
                                         thumbnail=str(thumb_path))
        else:
            res = upload_photo_post(cl, account["username"], publish_path,
                                    caption, track=track)
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

        db.update_post(post_id, status="failed", error=res["error"],
                       error_stage="publish")
        raise RuntimeError(f"upload failed: {res['error']}")

    except Exception as e:  # noqa: BLE001 — top-level failure reporting
        msg = str(e)[:800]
        if post_id is not None:
            try:
                db.update_post(post_id, status="failed", error=msg,
                               error_stage="pipeline")
            except Exception:  # noqa: BLE001
                pass
        notify.error(msg)
        notes.append(msg)
        outcome["status"] = "failed"
        finish("failed", msg)
        return 2 if (args.strict and "placeholder" in msg) else 1
    finally:
        if clients:
            # Collect insights (views/likes/comments) before logging out.
            try:
                collect_insights(clients, limit=20, min_age_hours=0)
            except Exception:  # noqa: BLE001 — insights are best-effort
                pass
            logout_all(clients)
        report(outcome["status"], post_id, outcome["theme"], outcome["line"],
               outcome["info"], notes)
        cleanup_temp()
        db.checkpoint()


def run_repost(args) -> int:
    """Publish one already-built post's exact media to a second account.

    The owner wants ONE piece of content per run, posted to both pages. The
    first account runs the full pipeline; every other account calls this with
    that post's id, reusing the same image, video, caption and SLOWBURN track.
    """
    source_id = int(args.repost)
    run_id = db.start_run(args.slot)
    clients: dict = {}
    new_id = None
    notes: list = []
    outcome = {"status": "failed", "theme": "image-post", "line": None,
               "info": None}

    def finish(status_: str, error: str | None = None) -> None:
        db.finish_run(run_id, status_, post_id=new_id or source_id, error=error)

    try:
        source = db.get_post(source_id)
        if not source:
            raise RuntimeError(f"repost: post {source_id} not found")
        if source.get("status") != "published":
            raise RuntimeError(f"repost: post {source_id} is not published")

        media = source.get("video_path") or source.get("final_image_path")
        if not media or not Path(media).exists():
            raise RuntimeError(f"repost: media missing at {media}")
        thumb = source.get("final_image_path")
        if (not thumb or not Path(thumb).exists()
                or Path(thumb).stat().st_size < 1000):
            # The original composed still may not be present in a fresh
            # runner. instagrapi needs an explicit thumbnail for Reel music,
            # so derive one from the video's first frame instead.
            import subprocess

            from config import FFMPEG_BIN

            fallback = TMP_DIR / f"repost_thumb_{source_id}.jpg"
            subprocess.run(
                [FFMPEG_BIN, "-y", "-loglevel", "error", "-i", media,
                 "-frames:v", "1", "-q:v", "2", str(fallback)],
                capture_output=True, timeout=60, check=False)
            thumb = str(fallback) if fallback.exists() else None
        print(f"[*] Thumbnail: {thumb}")

        usable = [a for a in ACCOUNTS if a["username"] and a["password"]
                  and (not IG_ACTIVE_ACCOUNT or a["name"] == IG_ACTIVE_ACCOUNT)]
        if not usable:
            raise RuntimeError("repost: no target account configured")
        account = usable[0]
        if (MIN_GAP_MINUTES and
                db.minutes_since_last_publish(account["name"]) < MIN_GAP_MINUTES):
            age = db.minutes_since_last_publish(account["name"])
            print(f"[=] {account['name']}: last publish {age:.1f} min ago "
                  f"(min gap {MIN_GAP_MINUTES}) — repost skipped")
            outcome["status"] = "skipped"
            finish("skipped", "min-gap")
            return 0
        if (DAILY_CAP_PER_ACCOUNT and
                db.count_published_today(account["name"]) >= DAILY_CAP_PER_ACCOUNT):
            print(f"[=] {account['name']}: daily cap reached — repost skipped")
            outcome["status"] = "skipped"
            finish("skipped", "daily-cap")
            return 0

        clients[account["name"]] = login_account(account)
        cl = clients[account["name"]]
        caption = source.get("caption_text") or ""
        dup = find_duplicate(cl, account["username"], caption, lookback=12)
        if dup:
            print(f"[=] {account['name']}: caption already live — repost skipped")
            db.update_post(source_id, error=f"repost duplicate on "
                                            f"{account['name']} (pk={dup})")
            outcome["status"] = "skipped"
            finish("skipped", "duplicate-caption")
            return 0

        meta = {}
        try:
            meta = json.loads(source.get("prompt_metadata") or "{}")
        except (ValueError, TypeError):
            pass
        track = None
        if MUSIC_ENABLED and (meta.get("music") or {}).get("source") != "local_bank":
            track = track_from_metadata(cl, meta.get("music"))
        if meta.get("music"):
            label = f"{meta['music'].get('title')} — {meta['music'].get('artist')}"
            print(f"[*] Music : {label} (same track as original)")

        fields = {
            "account": account["name"], "theme": source.get("theme") or "image-post",
            "title": source.get("title"), "engine": source.get("engine"),
            "caption_text": caption, "quote_id": source.get("quote_id"),
            "quote_text": source.get("quote_text"),
            "prompt_text": source.get("prompt_text"),
            "prompt_metadata": source.get("prompt_metadata"),
            "provider": source.get("provider"), "model": source.get("model"),
            "seed": source.get("seed"), "image_path": source.get("image_path"),
            "image_source": source.get("image_source"),
            "final_image_path": source.get("final_image_path"),
            "video_path": source.get("video_path"),
            "generation_status": source.get("generation_status"),
            "generation_path": source.get("generation_path"),
            "composition_status": source.get("composition_status"),
            "output_kind": source.get("output_kind"),
            "duration_sec": source.get("duration_sec"),
            "status": "publishing",
        }
        new_id = db.insert_post(**fields)
        outcome["line"] = source.get("quote_text")
        outcome["info"] = {"path": media, "image": thumb}
        print(f"[*] Repost to {account['name']} ({account['username']}): "
              f"post #{source_id} -> #{new_id}")

        if (source.get("output_kind") == "reel") or str(media).endswith(".mp4"):
            res = upload_reel_with_music(cl, account["username"], media,
                                         caption, track=track, thumbnail=thumb)
        else:
            res = upload_photo_post(cl, account["username"], media,
                                    caption, track=track)
        if not res["ok"]:
            db.update_post(new_id, status="failed", error=res["error"],
                           error_stage="publish")
            raise RuntimeError(f"repost upload failed: {res['error']}")

        permalink = (f"https://www.instagram.com/p/{res['code']}/"
                     if res.get("code") else None)
        db.update_post(new_id, status="published", ig_id=res.get("pk"),
                       permalink=permalink,
                       published_at=datetime.now().isoformat(timespec="seconds"))
        print(f"[+] Published: {permalink or res.get('pk')}")
        outcome["status"] = "published"
        finish("published")
        return 0
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:800]
        if new_id is not None:
            try:
                db.update_post(new_id, status="failed", error=msg,
                               error_stage="repost")
            except Exception:  # noqa: BLE001
                pass
        notify.error(msg)
        notes.append(msg)
        outcome["status"] = "failed"
        finish("failed", msg)
        return 1
    finally:
        if clients:
            logout_all(clients)
        report(outcome["status"], new_id or source_id, outcome["theme"],
               outcome["line"], outcome["info"], notes)
        cleanup_temp()
        db.checkpoint()


def run_reel(args) -> int:
    """Legacy video Reel flow retained for backward compatibility."""
    import generate_ai_image
    from generate_video import render_reel

    dry = args.dry_run or DRY_RUN
    run_id = db.start_run(args.slot)
    clients: dict = {}
    post_id = None
    notes: list = []
    outcome = {"status": "failed", "theme": None, "line": None, "info": None}

    def finish(status_: str, error: str | None = None) -> None:
        db.finish_run(run_id, status_, post_id=post_id, error=error)

    try:
        if KILL_SWITCH or (BASE_DIR / "data" / "KILL_SWITCH").exists():
            outcome["status"] = "skipped"
            finish("skipped")
            return 0
        usable = [a for a in ACCOUNTS if a["username"] and a["password"]
                  and (not IG_ACTIVE_ACCOUNT or a["name"] == IG_ACTIVE_ACCOUNT)]
        if not usable and not dry:
            raise RuntimeError("no accounts configured")
        for acct in usable:
            try:
                clients[acct["name"]] = login_account(acct)
            except Exception as e:  # noqa: BLE001
                notes.append(f"{acct['name']}: {e}")
        recover = getattr(db, "recent_posts_need_recovery", None)
        if recover:
            recover()
        else:
            db.stale_publishing(min_age_minutes=5)
        account = pick_account(clients)
        if not account and not dry:
            outcome["status"] = "skipped"
            finish("skipped", "daily-cap")
            return 0
        account = account or {"name": "dry-run", "username": "(none)",
                              "handle": "@xene_hotty"}
        theme = choose_theme(args.theme)
        meta = theme_meta(theme)
        import lines as lines_mod
        line, engine = lines_mod.compose(theme, meta["mood"])
        outcome.update(theme=theme, line=line)
        post_id = db.insert_post(account=account["name"], theme=theme,
                                 title=line, engine=engine, status="building")
        if args.skip_generate:
            image, source = newest_image(), "existing"
            if image is None:
                raise RuntimeError("--skip-generate set but no images found")
        else:
            image, source = generate_ai_image.generate(theme=theme)
        if args.strict and source == "placeholder":
            raise RuntimeError("STRICT: placeholder image refused")
        track = pick_track(theme)
        info = render_reel(
            image, track, line, mode="story",
            variant=random.choice(["upper", "center", "lower"]),
            output_name=f"reel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        outcome["info"] = info
        db.update_post(post_id, video_path=info["path"], image_path=str(image),
                       image_source=source, music_path=info["music"],
                       variant=info["variant"], duration_sec=info["duration"])
        ok, reasons, vinfo = validate_video(info["path"])
        if not ok:
            raise RuntimeError("video validation failed: " + ", ".join(reasons))
        credit = MUSIC_CREDIT if track else ""
        caption = lines_mod.build_caption(theme, meta["mood"], line, credit=credit)
        db.update_post(post_id, caption_text=caption, status="built")
        if dry:
            outcome["status"] = "dry-run"
            finish("dry-run")
            return 0
        cl = clients[account["name"]]
        if find_duplicate(cl, account["username"], caption, lookback=12):
            outcome["status"] = "skipped"
            finish("skipped", "duplicate-caption")
            return 0
        db.update_post(post_id, status="publishing")
        res = upload_reel(cl, account["username"], info["path"], caption)
        if res["ok"]:
            db.update_post(post_id, status="published", ig_id=res.get("pk"),
                           published_at=datetime.now().isoformat(
                               timespec="seconds"))
            outcome["status"] = "published"
            finish("published")
            return 0
        raise RuntimeError(f"upload failed: {res['error']}")
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:800]
        notify.error(msg)
        notes.append(msg)
        outcome["status"] = "failed"
        finish("failed", msg)
        return 1
    finally:
        if clients:
            logout_all(clients)
        report(outcome["status"], post_id, outcome["theme"], outcome["line"],
               outcome["info"], notes)
        cleanup_temp()
        db.checkpoint()


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate, compose and publish one glamour quote image")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build only, never publish")
    parser.add_argument("--skip-generate", action="store_true",
                        help="Reuse the newest generated image in assets/images")
    parser.add_argument("--strict", action="store_true",
                        help="Never accept a placeholder; fail instead")
    parser.add_argument("--mode", choices=["reel", "photo", "legacy-reel"],
                        default="reel",
                        help="Output mode (reel = composed image as Reel + trending audio, default)")
    parser.add_argument("--theme", default=None,
                        help="Legacy theme (only used with --mode legacy-reel)")
    parser.add_argument("--variation", default=None,
                        choices=COMPOSE_VARIANTS,
                        help="Force text placement variant")
    parser.add_argument("--slot", default="cron",
                        help="Run label stored in the runs table")
    parser.add_argument("--repost", type=int, default=None,
                        help="Publish an existing post's exact media to this "
                             "run's account (one content, both pages)")
    parser.add_argument("--force", action="store_true",
                        help="Publish even if cadence guards would skip")
    args = parser.parse_args(argv)

    if RANDOM_SEED:
        random.seed(int(RANDOM_SEED))

    if args.repost:
        return run_repost(args)
    if args.mode == "legacy-reel":
        return run_reel(args)
    return run_image(args)


if __name__ == "__main__":
    sys.exit(run())
