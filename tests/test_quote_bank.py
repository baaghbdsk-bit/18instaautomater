"""Tests for the curated quote bank loader, selector and safe appender."""

import hashlib
import json
import random

import pytest

import lines
import quote_bank as qb
from config import QUOTE_BANK_PATH, QUOTE_LOW_WATERMARK

ORIGINAL_BANK_PATH = QUOTE_BANK_PATH


@pytest.fixture(autouse=True)
def synthetic_bank(tmp_path, monkeypatch):
    """Give the loader tests a deterministic 110-line bank.

    The shipped bank is intentionally empty while the user curates their 500
    approved lines, so generic loader/selection tests must not depend on it.
    """
    entries = []
    i = 0
    for mood in ("flirty", "bold", "dreamy"):
        for text in lines.SEED[mood]:
            i += 1
            entries.append({"id": f"q{i:03d}", "text": text, "mood": mood,
                            "tags": []})
    for j in range(20):
        i += 1
        entries.append({
            "id": f"q{i:03d}",
            "text": f"This is a curated sample line number {j + 1} for tests",
            "mood": ("flirty", "bold", "dreamy")[j % 3],
            "tags": [],
        })
    p = tmp_path / "synthetic_bank.json"
    p.write_text(json.dumps({"version": 1, "source": "test", "lines": entries}),
                 encoding="utf-8")
    monkeypatch.setattr(qb, "QUOTE_BANK_PATH", p)
    import config
    monkeypatch.setattr(config, "QUOTE_BANK_PATH", p)
    yield


# ---------------------------------------------------------------------------
# the shipped bank (user-managed; currently empty by design)
# ---------------------------------------------------------------------------
def test_shipped_bank_is_valid_whenever_loaded():
    raw = json.loads(ORIGINAL_BANK_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw.get("lines"), list)
    assert all(isinstance(x.get("id"), str) and isinstance(x.get("text"), str)
               and x["text"].strip() and isinstance(x.get("mood"), str)
               for x in raw["lines"])


def test_unique_ids():
    bank = qb.load_bank()
    ids = [q.id for q in bank]
    assert len(ids) == len(set(ids)) == 110
    assert ids == [f"q{i:03d}" for i in range(1, 111)]


def test_original_seeds_preserved_exactly():
    """All 90 shipped seeds appear verbatim, in order, with original mood."""
    bank = qb.load_bank()
    seeds = bank[:90]
    index = 0
    for mood in ("flirty", "bold", "dreamy"):
        for text in lines.SEED[mood]:
            q = seeds[index]
            assert q.text == text                 # exact wording, no normalising
            assert q.mood == mood
            index += 1
    assert index == 90

    # A few known lines spelled out, as an independent guard.
    assert bank[0].text == "Bet you can't look away from this one"
    assert bank[30].text == "Confidence looks this good on me"
    assert bank[60].text == "Lost in a daydream about you again"


def test_twenty_new_lines_have_valid_shape():
    bank = qb.load_bank()
    new = bank[90:]
    assert len(new) == 20
    assert len({q.id for q in new}) == 20
    assert {q.mood for q in new} <= {"flirty", "bold", "dreamy"}
    for q in new:
        assert 18 <= len(q.text) <= 118
        assert q.text.strip() == q.text
        assert all(isinstance(t, str) for t in q.tags)


def test_load_bank_unknown_extra_fields_ignored(tmp_path):
    p = tmp_path / "bank.json"
    p.write_text(json.dumps({
        "version": 1,
        "source": "curated-approved-bank",
        "unexpected": "ignored",
        "lines": [{
            "id": "x1", "text": "Hello there, this is a line", "mood": "flirty",
            "tags": ["tease"], "mystery": 42,
        }],
    }), encoding="utf-8")
    bank = qb.load_bank(p)
    assert bank == [qb.Quote("x1", "Hello there, this is a line", "flirty",
                             ["tease"])]


def test_load_bank_errors(tmp_path):
    missing = tmp_path / "nope.json"
    with pytest.raises(FileNotFoundError):
        qb.load_bank(missing)

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        qb.load_bank(bad)

    no_lines = tmp_path / "nolines.json"
    no_lines.write_text(json.dumps({"version": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="'lines'"):
        qb.load_bank(no_lines)

    dupes = tmp_path / "dupes.json"
    dupes.write_text(json.dumps({"lines": [
        {"id": "a", "text": "first line here", "mood": "flirty"},
        {"id": "a", "text": "second line here", "mood": "bold"},
    ]}), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate quote id"):
        qb.load_bank(dupes)

    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"lines": [
        {"id": "a", "text": "   ", "mood": "flirty"},
    ]}), encoding="utf-8")
    with pytest.raises(ValueError, match="empty 'text'"):
        qb.load_bank(empty)


def test_default_path_is_config_path():
    # load_bank() with no argument must read the configured bank.
    assert qb.load_bank() == qb.load_bank(qb.QUOTE_BANK_PATH)


# ---------------------------------------------------------------------------
# selection
# ---------------------------------------------------------------------------
def test_select_unused_prefers_bank_order_and_skips_used():
    bank = qb.load_bank()
    assert qb.select_unused(bank, set()).id == "q001"
    assert qb.select_unused(bank, {"q001"}).id == "q002"
    assert qb.select_unused(bank, {"q001", "q002"}).id == "q003"


def test_select_unused_never_returns_duplicates():
    bank = qb.load_bank()
    used = set()
    seen = []
    for _ in range(len(bank)):
        pick = qb.select_unused(bank, used)
        assert pick is not None
        assert pick.id not in used
        used.add(pick.id)
        seen.append(pick.id)
    assert len(set(seen)) == len(bank) == 110


def test_exhaustion_returns_none():
    bank = qb.load_bank()
    used = {q.id for q in bank}
    assert qb.select_unused(bank, used) is None
    assert qb.select_unused(bank, used, rng=random.Random(1)) is None
    assert qb.unused_count(bank, used) == 0


def test_unused_count():
    bank = qb.load_bank()
    assert qb.unused_count(bank, set()) == 110
    assert qb.unused_count(bank, {"q001", "q005"}) == 108


def test_seeded_rng_determinism():
    bank = qb.load_bank()
    a = [qb.select_unused(bank, set(), rng=random.Random(42)).id
         for _ in range(10)]
    b = [qb.select_unused(bank, set(), rng=random.Random(42)).id
         for _ in range(10)]
    assert a == b
    assert all(qb.select_unused(bank, set(), rng=random.Random(i)) is not None
               for i in range(5))


def test_seeded_rng_never_picks_used():
    bank = qb.load_bank()
    used = {q.id for q in bank[:100]}
    for seed in range(20):
        pick = qb.select_unused(bank, used, rng=random.Random(seed))
        assert pick.id not in used
        assert int(pick.id[1:]) > 100


# ---------------------------------------------------------------------------
# low-water mark + status
# ---------------------------------------------------------------------------
def test_is_low():
    bank = qb.load_bank()
    assert qb.is_low(bank, set()) is False
    # 90 used -> 20 unused, exactly at the configured watermark.
    used = {q.id for q in bank[:90]}
    assert qb.unused_count(bank, used) == QUOTE_LOW_WATERMARK
    assert qb.is_low(bank, used) is True
    assert qb.is_low(bank, used, watermark=10) is False
    assert qb.is_low(bank, used, watermark=20) is True
    assert qb.is_low(bank, {q.id for q in bank[:95]}, watermark=20) is True


def test_format_bank_status():
    bank = qb.load_bank()
    status = qb.format_bank_status(bank, set())
    assert isinstance(status, str)
    assert "110 total" in status
    assert "0 used" in status
    assert "110 unused" in status
    assert "[OK]" in status
    low_status = qb.format_bank_status(bank, {q.id for q in bank[:95]})
    assert "[LOW]" in low_status


# ---------------------------------------------------------------------------
# safe append
# ---------------------------------------------------------------------------
def test_add_lines_dedupes(tmp_path):
    p = tmp_path / "bank.json"
    p.write_text(json.dumps({
        "version": 1,
        "source": "curated-approved-bank",
        "lines": [
            {"id": "q001", "text": "An existing line about the night",
             "mood": "flirty", "tags": ["tease"]},
        ],
    }), encoding="utf-8")

    added = qb.add_lines(p, [
        {"id": "q001", "text": "Duplicate id, must be skipped", "mood": "bold"},
        {"id": "q002", "text": "A brand new line about the stars",
         "mood": "dreamy", "tags": ["dreamy"]},
        {"id": "q002", "text": "Another with the same new id", "mood": "bold"},
        {"id": "q003", "text": "A third brand new line for us", "mood": "bold"},
    ])
    assert added == 2

    bank = qb.load_bank(p)
    assert [q.id for q in bank] == ["q001", "q002", "q003"]
    assert [q.text for q in bank] == [
        "An existing line about the night",
        "A brand new line about the stars",
        "A third brand new line for us",
    ]
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert raw["source"] == "curated-approved-bank"


def test_add_lines_noop_on_all_duplicates(tmp_path):
    p = tmp_path / "bank.json"
    existing = {"lines": [
        {"id": "q001", "text": "An existing line about the night", "mood": "flirty"},
    ]}
    p.write_text(json.dumps(existing), encoding="utf-8")
    before = p.read_bytes()
    added = qb.add_lines(p, [
        {"id": "q001", "text": "A different text but same id", "mood": "bold"},
    ])
    assert added == 0
    assert p.read_bytes() == before          # untouched, byte for byte


def test_add_lines_does_not_mutate_on_invalid_input(tmp_path):
    p = tmp_path / "bank.json"
    original = {
        "version": 1,
        "source": "curated-approved-bank",
        "lines": [
            {"id": "q001", "text": "An existing line about the night",
             "mood": "flirty", "tags": ["tease"]},
        ],
    }
    p.write_text(json.dumps(original), encoding="utf-8")
    before = p.read_bytes()

    # The batch contains a valid entry followed by an invalid one: the whole
    # operation must abort without writing anything.
    with pytest.raises(ValueError):
        qb.add_lines(p, [
            {"id": "q002", "text": "A perfectly valid new line here",
             "mood": "bold"},
            {"id": "q003", "text": "   "},       # empty text -> invalid
        ])
    assert p.read_bytes() == before
    assert qb.load_bank(p) == qb.load_bank(p)  # still loads cleanly
    assert [q.id for q in qb.load_bank(p)] == ["q001"]


def test_add_lines_creates_bank_when_missing(tmp_path):
    p = tmp_path / "new_bank.json"
    added = qb.add_lines(p, [
        {"id": "q001", "text": "First line in a brand new bank", "mood": "flirty"},
    ])
    assert added == 1
    assert [q.id for q in qb.load_bank(p)] == ["q001"]


def test_add_lines_accepts_quote_objects_and_ignores_extras(tmp_path):
    p = tmp_path / "bank.json"
    p.write_text(json.dumps({"lines": []}), encoding="utf-8")
    added = qb.add_lines(p, [
        qb.Quote("z1", "A quote object with a long enough text",
                 "bold", ["confidence"]),
        {"id": "z2", "text": "A dict with extra ignored fields", "mood": "flirty",
         "tags": "tease", "junk": True},
    ])
    assert added == 2
    bank = qb.load_bank(p)
    assert bank[0].tags == ["confidence"]
    assert bank[1].tags == ["tease"]


# ---------------------------------------------------------------------------
# fingerprint
# ---------------------------------------------------------------------------
def test_bank_fingerprint_stable():
    bank = qb.load_bank()
    fp = qb.bank_fingerprint(bank)
    assert isinstance(fp, str)
    assert len(fp) == hashlib.sha256().digest_size * 2
    assert fp == qb.bank_fingerprint(qb.load_bank())       # reload -> same
    assert fp == qb.bank_fingerprint(list(bank))           # list copy -> same

    # Order matters, and text matters.
    assert fp != qb.bank_fingerprint(list(reversed(bank)))
    changed = [qb.Quote(q.id, q.text + "!", q.mood, q.tags) for q in bank]
    assert fp != qb.bank_fingerprint(changed)


def test_bank_fingerprint_matches_manual_digest():
    bank = [qb.Quote("a", "text one", "flirty", []),
            qb.Quote("b", "text two", "bold", [])]
    h = hashlib.sha256()
    for qid, text in (("a", "text one"), ("b", "text two")):
        h.update(qid.encode("utf-8"))
        h.update(b"\x1f")
        h.update(text.encode("utf-8"))
        h.update(b"\x1e")
    assert qb.bank_fingerprint(bank) == h.hexdigest()
