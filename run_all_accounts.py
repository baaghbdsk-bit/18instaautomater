"""
run_all_accounts.py — one piece of content per run, published to every account.

GitHub Actions calls this script. The first configured account runs the full
pipeline (quote -> image -> Reel -> caption -> publish). Every other account
then calls ``pipeline.py --repost <post_id>`` to publish that SAME video,
image, caption and SLOWBURN track to its own page.

Each account keeps its own session, daily cap and duplicate-caption guard. A
failure on one account never blocks the others.

Usage:
    python run_all_accounts.py                     # all configured accounts
    python run_all_accounts.py --dry-run           # build only, publish nothing
    python run_all_accounts.py --only account_1    # single account
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys

import db
from config import ACCOUNTS
import post_youtube


def _latest_published(account_name: str, after_id: int) -> int | None:
    """Find the post id created by the full pipeline run we just finished."""
    rows = db.recent_posts(limit=10, account=account_name)
    ids = [int(r["id"]) for r in rows
           if int(r["id"]) > after_id and r.get("status") == "published"]
    return max(ids) if ids else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build once, post to all accounts")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true", default=True)
    parser.add_argument("--slot", default="cron")
    parser.add_argument("--only", default=None,
                        help="Restrict to one account name (e.g. account_1)")
    parser.add_argument("--mode", default="reel",
                        choices=["reel", "photo", "legacy-reel"])
    args = parser.parse_args()

    targets = [a for a in ACCOUNTS if a.get("username") and a.get("password")]
    if args.only:
        targets = [a for a in targets if a["name"] == args.only]
    if not targets:
        print("[!] No configured accounts with credentials — nothing to run.")
        return 1

    baseline = max((int(r["id"]) for r in db.recent_posts(limit=200)), default=0)
    failures = 0
    source_id: int | None = None

    for idx, acc in enumerate(targets):
        print(f"\n{'=' * 64}")
        print(f"  ACCOUNT {acc['name']} ({acc['username']})")
        print('=' * 64)
        env = os.environ.copy()
        env["IG_ACTIVE_ACCOUNT"] = acc["name"]

        if idx == 0 or args.dry_run or source_id is None:
            # First account, dry run, or fallback when prior account failed: build from scratch.
            cmd = [sys.executable, "pipeline.py", "--strict", "--slot",
                   f"{args.slot}-{acc['name']}", "--mode", args.mode]
            if args.dry_run:
                cmd.append("--dry-run")
            rc = subprocess.run(cmd, env=env).returncode
            if rc == 0 and not args.dry_run and source_id is None:
                source_id = _latest_published(acc["name"], baseline)
                if source_id is None:
                    print("[!] Could not identify the post just published — "
                          "remaining accounts will build their own content.")
        else:
            # Same content, same music, different page.
            cmd = [sys.executable, "pipeline.py", "--strict", "--slot",
                   f"{args.slot}-{acc['name']}", "--mode", args.mode,
                   "--repost", str(source_id)]
            rc = subprocess.run(cmd, env=env).returncode

        if rc != 0:
            failures += 1
            print(f"[!] {acc['name']} failed (exit {rc}) — continuing.")
        else:
            role = "original" if idx == 0 or args.dry_run else "same content"
            print(f"[+] {acc['name']} completed ({role}).")

    # If at least one post was published and YouTube is configured, upload to YouTube Shorts
    if source_id is not None and not args.dry_run and post_youtube.is_configured():
        post_data = db.get_post(source_id)
        if post_data and post_data.get("video_path"):
            v_path = Path(post_data["video_path"])
            if v_path.exists():
                print(f"\n{'=' * 64}")
                print("  YOUTUBE SHORTS PUBLISHING")
                print('=' * 64)
                title = post_data.get("title") or post_data.get("quote_text") or "Reel"
                desc = post_data.get("caption_text") or ""
                yt_res = post_youtube.upload_short(video_path=v_path, title=title, description=desc)
                if yt_res.get("ok"):
                    print(f"[+] YouTube Shorts published: {yt_res['url']}")
                else:
                    print(f"[!] YouTube upload failed: {yt_res.get('error')}")
            else:
                print(f"[-] Video file missing for YouTube upload: {v_path}")
    elif not post_youtube.is_configured():
        print("[i] YouTube not configured — skipping YouTube Shorts (run setup_youtube.py to enable).")

    print(f"\nDone. {len(targets) - failures}/{len(targets)} account(s) succeeded.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
