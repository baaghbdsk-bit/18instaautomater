"""
quote_bank.py — curated, approved quote bank utilities.

Pure module: only the standard library plus ``config`` (no DB import, so it
cannot introduce circular imports). The bank itself is an on-disk JSON file
(``config.QUOTE_BANK_PATH``) that is hand-curated and approved — LLM generation
is deliberately NOT used to fill it.

The stored text is treated as opaque: loaders never normalise, trim or rewrite
a line's wording. Validation is limited to what keeps the bank well formed
(unique ids, non-empty text) and unknown extra fields are ignored.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from config import QUOTE_BANK_PATH, QUOTE_LOW_WATERMARK

__all__ = [
    "Quote",
    "load_bank",
    "select_unused",
    "unused_count",
    "is_low",
    "format_bank_status",
    "add_lines",
    "bank_fingerprint",
]

_DEFAULT_VERSION = 1
_DEFAULT_SOURCE = "curated-approved-bank"


@dataclass
class Quote:
    """A single approved line."""

    id: str
    text: str
    mood: str
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------
def _coerce_tags(value) -> List[str]:
    """Normalise the ``tags`` field into a list of strings (never stored raw)."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(t) for t in value]
    raise ValueError("quote 'tags' must be a list of strings")


def _quote_from_obj(obj) -> Quote:
    """Validate + build a Quote from a dict or Quote, ignoring extra fields."""
    if isinstance(obj, Quote):
        qid, text = obj.id, obj.text
        mood, tags = obj.mood, obj.tags
    elif isinstance(obj, dict):
        qid = obj.get("id")
        text = obj.get("text")
        mood = obj.get("mood", "")
        tags = obj.get("tags")
        # Unknown keys in obj are intentionally ignored.
    else:
        raise ValueError(f"quote entry must be an object, got {type(obj).__name__}")

    if not isinstance(qid, str) or not qid.strip():
        raise ValueError("quote 'id' must be a non-empty string")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"quote {qid!r} has empty 'text'")
    if mood is None:
        mood = ""
    if not isinstance(mood, str):
        raise ValueError(f"quote {qid!r} has a non-string 'mood'")
    return Quote(id=qid, text=text, mood=mood, tags=_coerce_tags(tags))


def _quote_to_dict(q: Quote) -> dict:
    return {"id": q.id, "text": q.text, "mood": q.mood, "tags": list(q.tags)}


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON via a temp file in the same dir, then os.replace (atomic)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=".quote_bank-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:  # pragma: no cover - exercised only on OS failure
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------
def load_bank(path=None) -> List[Quote]:
    """
    Load and validate the approved quote bank.

    ``path`` defaults to ``config.QUOTE_BANK_PATH``. Returns a list of
    :class:`Quote` in on-disk order. Raises ``FileNotFoundError`` for a missing
    file and ``ValueError`` for malformed JSON, a malformed ``lines`` field,
    duplicate ids or empty text. Unknown extra fields are ignored.
    """
    bank_path = Path(path) if path is not None else Path(QUOTE_BANK_PATH)

    if not bank_path.is_file():
        raise FileNotFoundError(f"Quote bank not found: {bank_path}")

    try:
        raw = bank_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read quote bank {bank_path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in quote bank {bank_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Quote bank {bank_path} must contain a JSON object")
    lines = data.get("lines")
    if not isinstance(lines, list):
        raise ValueError(f"Quote bank {bank_path} is missing a 'lines' list")

    bank: List[Quote] = []
    seen: set[str] = set()
    for index, entry in enumerate(lines):
        try:
            quote = _quote_from_obj(entry)
        except ValueError as exc:
            raise ValueError(f"Invalid quote at index {index}: {exc}") from exc
        if quote.id in seen:
            raise ValueError(f"Duplicate quote id in bank: {quote.id!r}")
        seen.add(quote.id)
        bank.append(quote)
    return bank


# ---------------------------------------------------------------------------
# selection
# ---------------------------------------------------------------------------
def _unused(bank: Iterable[Quote], used_ids: Iterable[str]) -> List[Quote]:
    used = set(used_ids or ())
    return [q for q in bank if q.id not in used]


def select_unused(bank: Sequence[Quote], used_ids: Iterable[str],
                  rng=None) -> Optional[Quote]:
    """
    Return an unused quote, or ``None`` when every quote has been used.

    With no ``rng`` the first unused quote in bank order is returned (fully
    deterministic). With an ``rng`` (e.g. ``random.Random(42)``) a random
    unused quote is chosen via ``rng.choice``, so a seeded rng is repeatable.
    """
    available = _unused(bank, used_ids)
    if not available:
        return None
    if rng is None:
        return available[0]
    return rng.choice(available)


def unused_count(bank: Iterable[Quote], used_ids: Iterable[str]) -> int:
    """Number of quotes in ``bank`` whose id is not in ``used_ids``."""
    return len(_unused(bank, used_ids))


def is_low(bank: Iterable[Quote], used_ids: Iterable[str],
           watermark: Optional[int] = None) -> bool:
    """
    True when unused quotes have dropped to the low-water mark or below.

    ``watermark`` defaults to ``config.QUOTE_LOW_WATERMARK``.
    """
    limit = QUOTE_LOW_WATERMARK if watermark is None else watermark
    return unused_count(bank, used_ids) <= limit


def format_bank_status(bank: Iterable[Quote], used_ids: Iterable[str]) -> str:
    """Human-readable one-line status (total / used / unused / low flag)."""
    bank_list = list(bank)
    total = len(bank_list)
    unused = unused_count(bank_list, used_ids)
    used = total - unused
    low = "LOW" if is_low(bank_list, used_ids) else "OK"
    return (
        f"Quote bank: {total} total, {used} used, {unused} unused "
        f"[{low}]"
    )


# ---------------------------------------------------------------------------
# appending / fingerprinting
# ---------------------------------------------------------------------------
def add_lines(path, new_lines) -> int:
    """
    Safely append ``new_lines`` to the bank file and return the number added.

    Each entry may be a dict (id/text/mood/tags, extra fields ignored) or a
    :class:`Quote`. Entries whose id already exists — in the bank or earlier in
    ``new_lines`` — are skipped (first occurrence wins). All entries are
    validated *before* anything is written, so invalid input leaves the file
    untouched. Writes are atomic (temp file + ``os.replace``).
    """
    bank_path = Path(path)

    if bank_path.is_file():
        bank = load_bank(bank_path)
        try:
            raw = json.loads(bank_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raw = {}
        except (OSError, json.JSONDecodeError):  # pragma: no cover - defensive
            raw = {}
    else:
        bank = []
        raw = {}

    # Validate the entire batch up front; a bad entry aborts before any write.
    validated = [_quote_from_obj(entry) for entry in new_lines]

    existing_ids = {q.id for q in bank}
    additions: List[Quote] = []
    for quote in validated:
        if quote.id in existing_ids:
            continue
        existing_ids.add(quote.id)
        additions.append(quote)

    if not additions:
        return 0

    payload = {
        "version": raw.get("version", _DEFAULT_VERSION),
        "source": raw.get("source", _DEFAULT_SOURCE),
        "lines": [_quote_to_dict(q) for q in bank + additions],
    }
    _atomic_write_json(bank_path, payload)
    return len(additions)


def bank_fingerprint(bank: Iterable[Quote]) -> str:
    """SHA-256 over ordered ids + texts (for DB metadata / change detection)."""
    digest = hashlib.sha256()
    for quote in bank:
        digest.update(quote.id.encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(quote.text.encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()
