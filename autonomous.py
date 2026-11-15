"""
autonomous.py
-------------
Runs 18instaautomater infinitely.

Each cycle:
  1. Runs main.py (posts up to MAX_POSTS_PER_RUN videos)
  2. Sleeps a long break (default 2–4 hours)
  3. Repeats forever

Use this for 24/7 unattended posting. Press Ctrl+C to stop.

Setup:
  pip install -r requirements.txt
  cp .env.example .env   # fill in credentials
  python autonomous.py
"""

import subprocess
import sys
import time
import random
from pathlib import Path

PYTHON_EXE = sys.executable
MAIN_SCRIPT = Path(__file__).resolve().parent / "main.py"

# Long break between cycles (seconds)
CYCLE_BREAK_MIN = 2 * 60 * 60   # 2 hours
CYCLE_BREAK_MAX = 4 * 60 * 60   # 4 hours

# If a cycle fails hard, wait this long before retrying
ERROR_RETRY_MIN = 30 * 60       # 30 min
ERROR_RETRY_MAX = 60 * 60       # 60 min


def run_cycle() -> bool:
    """Run main.py once. Returns True if it completed, False if it errored."""
    print(f"\n{'='*60}")
    print(f"  AUTONOMOUS CYCLE START — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    result = subprocess.run([PYTHON_EXE, str(MAIN_SCRIPT)])

    if result.returncode == 0:
        print(f"\n[+] Cycle completed successfully at {time.strftime('%H:%M:%S')}")
        return True
    else:
        print(f"\n[!] Cycle exited with code {result.returncode} at {time.strftime('%H:%M:%S')}")
        return False


def main():
    print("="*60)
    print("  18INSTAAUTOMATER — AUTONOMOUS MODE")
    print("  Press Ctrl+C to stop")
    print("="*60)

    cycle = 0
    while True:
        cycle += 1
        print(f"\n--- Cycle #{cycle} ---")

        try:
            ok = run_cycle()
        except KeyboardInterrupt:
            print("\n[!] Stopped by user.")
            break
        except Exception as e:
            print(f"\n[!] Unexpected error: {e}")
            ok = False

        if ok:
            sleep_for = random.randint(CYCLE_BREAK_MIN, CYCLE_BREAK_MAX)
        else:
            sleep_for = random.randint(ERROR_RETRY_MIN, ERROR_RETRY_MAX)

        hours = sleep_for // 3600
        minutes = (sleep_for % 3600) // 60
        print(f"\n[*] Sleeping {hours}h {minutes}m before next cycle...")
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()