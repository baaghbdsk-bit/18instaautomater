"""
notify.py — failure reporting for CI and local runs.

Port of the reference engine's notify.js:
  * GitHub Actions ::error:: / ::warning:: annotations (trigger failure mail)
  * step summary markdown
  * optional Discord/Slack webhook
A notification failure is never fatal to the run.
"""

import json
import os
import sys
from pathlib import Path

from config import NOTIFY_WEBHOOK_URL


def _is_actions() -> bool:
    return os.getenv("GITHUB_ACTIONS", "").lower() == "true"


def annotate(kind: str, message: str) -> None:
    """kind: 'error' | 'warning' | 'notice'"""
    if _is_actions():
        # Newlines would break the annotation protocol.
        flat = str(message).replace("\r", " ").replace("\n", " | ")
        print(f"::{kind}::{flat}")
    else:
        prefix = {"error": "[!]", "warning": "[~]", "notice": "[i]"}.get(kind, "[*]")
        print(f"{prefix} {message}")


def webhook(text: str) -> None:
    if not NOTIFY_WEBHOOK_URL:
        return
    try:
        import requests
        payload = {"content": text, "text": text, "username": "reel-engine"}
        requests.post(NOTIFY_WEBHOOK_URL, json=payload, timeout=15)
    except Exception as e:  # noqa: BLE001 — notifications are fail-soft
        print(f"[notify] webhook failed: {e}")


def summary(markdown: str) -> None:
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"[notify] step summary failed: {e}")


def set_output(name: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")
    except Exception as e:  # noqa: BLE001
        print(f"[notify] set_output failed: {e}")


def error(message: str) -> None:
    annotate("error", message)
    webhook(f"❌ reel-engine: {message}")


def warn(message: str) -> None:
    annotate("warning", message)
