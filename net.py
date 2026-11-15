"""
net.py — retry / backoff primitives shared by every network call.

Port of the reference engine's net.js: jittered exponential backoff with an
explicit retryable classification, so a rate-limit is retried but a
validation error is not.
"""

import random
import time
from typing import Callable, Iterable, Optional


class HttpError(Exception):
    def __init__(self, status: int, body: str, url: str):
        # Never leak query strings (tokens live there).
        safe = url.split("?")[0]
        super().__init__(f"HTTP {status} for {safe}: {str(body)[:300]}")
        self.status = status
        self.body = body
        self.url = safe


def sleep(seconds: float) -> None:
    time.sleep(seconds)


def with_retry(
    fn: Callable,
    *,
    attempts: int = 4,
    base_ms: int = 1200,
    label: str = "call",
    is_retryable: Optional[Callable[[Exception], bool]] = None,
    sleep_fn: Callable[[float], None] = sleep,
):
    """
    Run fn() with jittered exponential backoff.

    Retryable by default: HttpError 429/5xx and anything that looks like a
    network problem (OSError, TimeoutError, ConnectionError). Classification
    can be overridden per call site via is_retryable.
    """
    last: Optional[Exception] = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — classified below
            last = e
            retryable = is_retryable(e) if is_retryable else _default_retryable(e)
            if not retryable or i == attempts - 1:
                raise
            delay = base_ms * (2 ** i) * (0.7 + random.random() * 0.6) / 1000.0
            print(f"[net] {label}: retry {i + 1}/{attempts - 1} in {delay:.1f}s "
                  f"({type(e).__name__}: {e})")
            sleep_fn(delay)
    raise last  # pragma: no cover — unreachable


def _default_retryable(e: Exception) -> bool:
    if isinstance(e, HttpError):
        return e.status == 429 or e.status >= 500
    if isinstance(e, (TimeoutError, ConnectionError, OSError)):
        return True
    # instagrapi / requests network errors carry these names.
    name = type(e).__name__.lower()
    return any(tok in name for tok in ("timeout", "connection", "network", "temporary"))


def request_with_retry(
    do_call: Callable[[], object],
    *,
    attempts: int = 4,
    base_ms: int = 1200,
    label: str = "http",
    is_retryable: Optional[Callable[[Exception], bool]] = None,
) -> object:
    return with_retry(do_call, attempts=attempts, base_ms=base_ms,
                      label=label, is_retryable=is_retryable)
