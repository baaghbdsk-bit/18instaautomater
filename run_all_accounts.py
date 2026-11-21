"""
run_all_accounts.py — run one full pipeline post for EACH configured account.

Used by GitHub Actions so a single scheduled run publishes once per account
(e.g. @xene_hotty and @panda_fcuk) while reusing the shared quote bank,
character identity, images and provider adapters.

Each sub-run is independent: a failure on one account never blocks the other.
The pipeline's own guards (daily cap, duplicate-caption, quote_usage claim)
still apply to every sub-run.

Usage:
    python run_all_accounts.py                     # all configured accounts
    python run_all_accounts.py --dry-run           # build only, no publishing
    python run_all_accounts.py --only account_1    # single account
"""

import argparse
import os
import subprocess
import sys

from config import ACCOUNTS


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the pipeline per account")
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

    failures = 0
    for acc in targets:
        print(f"\n{'=' * 64}")
        print(f"  ACCOUNT {acc['name']} ({acc['username']})")
        print('=' * 64)
        # The pipeline reads ACCOUNTS from config; pin it to this one account
        # so each run uses a single, unambiguous session and cadence bucket.
        env = os.environ.copy()
        env["IG_ACTIVE_ACCOUNT"] = acc["name"]
        cmd = [sys.executable, "pipeline.py", "--strict", "--slot",
               f"{args.slot}-{acc['name']}", "--mode", args.mode]
        if args.dry_run:
            cmd.append("--dry-run")
        rc = subprocess.run(cmd, env=env).returncode
        if rc != 0:
            failures += 1
            print(f"[!] {acc['name']} failed (exit {rc}) — continuing.")
        else:
            print(f"[+] {acc['name']} completed.")

    print(f"\nDone. {len(targets) - failures}/{len(targets)} account(s) succeeded.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
