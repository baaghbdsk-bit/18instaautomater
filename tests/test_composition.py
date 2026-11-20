"""Tests for static quote-image composition (Pillow only, no network/ffmpeg)."""

import hashlib
import json
import shutil

from PIL import Image, ImageOps, ImageStat

from compose_image import compose_quote_image, is_placeholder_image
from lines import strip_emoji
from validate import validate_final_image

QUOTE = "Bet you can't look away from this one, darling"
LONG_QUOTE = ("You were supposed to keep scrolling past me but here you are "
              "still watching every single thing I do tonight")
FONT_SIZES = (116, 108, 100, 92, 84, 76, 68)


def _source(path, size=(600, 900)):
    """A textured synthetic source (big enough to clear COMPOSE_MIN_BYTES)."""
    noise = Image.effect_noise(size, 60)
    img = ImageOps.colorize(noise, black=(18, 6, 40), white=(245, 200, 150))
    img.save(path, format="JPEG", quality=92)
    return path


def _band_mean(path, frac, half=80):
    """Mean luminance of a narrow side strip — avoids the centred text."""
    with Image.open(path) as im:
        y = int(frac * im.height)
        crop = im.crop((0, max(0, y - half), 70,
                        min(im.height, y + half)))
        return ImageStat.Stat(crop.convert("L")).mean[0]


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------
def test_cover_resize_and_return_shape(tmp_path):
    src = _source(tmp_path / "src.jpg", (400, 900))   # not 9:16
    out = tmp_path / "out.jpg"
    info = compose_quote_image(src, QUOTE, output_path=out)

    assert info["ok"] is True, info
    assert (info["width"], info["height"]) == (1080, 1920)
    assert info["variant"] == "lower"          # safe default call site
    assert info["bytes"] >= 20_000
    assert info["lines"]
    with Image.open(out) as im:
        assert im.size == (1080, 1920)         # exact cover fit
        assert im.mode == "RGB"
    assert info["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert info["is_placeholder"] is False
    assert info["source"] == str(src)


def test_long_quote_wraps_without_dropping_words(tmp_path):
    src = _source(tmp_path / "src.jpg")
    out = tmp_path / "long.jpg"
    info = compose_quote_image(src, LONG_QUOTE, output_path=out)

    assert info["ok"] is True, info
    assert 1 <= len(info["lines"]) <= 5        # 4 normally, 5 at layout fallback
    assert info["font_size"] in FONT_SIZES
    joined = " ".join(info["lines"])
    for word in ("scrolling", "watching", "tonight"):
        assert word in joined
    assert len(joined) >= len(strip_emoji(LONG_QUOTE)) - 4


def test_variant_changes_placement(tmp_path):
    src = _source(tmp_path / "src.jpg")
    up = compose_quote_image(src, QUOTE, output_path=tmp_path / "up.jpg",
                             variant="upper")
    low = compose_quote_image(src, QUOTE, output_path=tmp_path / "low.jpg",
                              variant="lower")
    assert up["ok"] is True and low["ok"] is True
    assert (up["variant"], low["variant"]) == ("upper", "lower")
    assert json.loads((tmp_path / "up.json").read_text("utf-8"))["variant"] == "upper"
    assert up["sha256"] != low["sha256"]

    # The scrim band follows the text: lower is darker at 0.63 H, upper at 0.30 H.
    assert _band_mean(tmp_path / "low.jpg", 0.63) < \
        _band_mean(tmp_path / "up.jpg", 0.63)
    assert _band_mean(tmp_path / "up.jpg", 0.30) < \
        _band_mean(tmp_path / "low.jpg", 0.30)


def test_sidecar_written(tmp_path):
    src = _source(tmp_path / "src.jpg")
    out = tmp_path / "sidecar.jpg"
    info = compose_quote_image(src, QUOTE, output_path=out, handle="@test")

    meta = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["lines"] == info["lines"]
    assert meta["quote"] == QUOTE
    assert meta["variant"] == "lower"
    assert meta["sha256"] == info["sha256"]
    assert meta["source"] == str(src)
    assert meta["bytes"] == info["bytes"]
    assert meta["handle"] == "@test"


def test_emoji_stripped_but_wording_preserved(tmp_path):
    src = _source(tmp_path / "src.jpg")
    quoted = "Stay a little longer, it gets better 🔥"
    info = compose_quote_image(src, quoted, output_path=tmp_path / "emoji.jpg")

    assert info["ok"] is True, info
    joined = " ".join(info["lines"])
    assert "🔥" not in joined
    assert "Stay a little longer" in joined
    meta = json.loads((tmp_path / "emoji.json").read_text("utf-8"))
    assert meta["quote"] == quoted


def test_failure_returns_error_dict(tmp_path):
    info = compose_quote_image(tmp_path / "missing.jpg", QUOTE,
                               output_path=tmp_path / "never.jpg")
    assert info["ok"] is False
    assert "error" in info
    assert info["variant"] == "lower"
    assert not (tmp_path / "never.jpg").exists()


# ---------------------------------------------------------------------------
# is_placeholder_image
# ---------------------------------------------------------------------------
def test_is_placeholder_image_detection(tmp_path):
    src = _source(tmp_path / "normal.jpg")
    assert is_placeholder_image(src) is False
    assert is_placeholder_image(tmp_path / "placeholder_dev.jpg") is True

    sidecar = src.with_suffix(".json")
    sidecar.write_text(json.dumps({"is_placeholder": True}), encoding="utf-8")
    assert is_placeholder_image(src) is True
    sidecar.write_text(json.dumps({"is_placeholder": False}), encoding="utf-8")
    assert is_placeholder_image(src) is False
    sidecar.write_text("not json", encoding="utf-8")
    assert is_placeholder_image(src) is False


# ---------------------------------------------------------------------------
# validate_final_image
# ---------------------------------------------------------------------------
def test_validate_final_image_passes(tmp_path):
    src = _source(tmp_path / "src.jpg")
    out = tmp_path / "good.jpg"
    info = compose_quote_image(src, QUOTE, output_path=out)
    assert info["ok"] is True, info

    ok, reasons, info = validate_final_image(out, must_contain_quote=QUOTE)
    assert ok is True, reasons
    assert info["size"] == (1080, 1920)
    assert info["mode"] == "RGB"
    assert info["bytes"] >= 20_000


def test_validate_rejects_placeholder_name(tmp_path):
    src = _source(tmp_path / "src.jpg")
    out = tmp_path / "good.jpg"
    assert compose_quote_image(src, QUOTE, output_path=out)["ok"] is True

    bad = tmp_path / "placeholder_copy.jpg"
    shutil.copy(out, bad)
    shutil.copy(out.with_suffix(".json"), bad.with_suffix(".json"))

    ok, reasons, _ = validate_final_image(bad, must_contain_quote=QUOTE)
    assert ok is False
    assert any("placeholder" in r for r in reasons)


def test_validate_rejects_wrong_size(tmp_path):
    src = _source(tmp_path / "src.jpg")
    out = tmp_path / "good.jpg"
    assert compose_quote_image(src, QUOTE, output_path=out)["ok"] is True

    ok, reasons, _ = validate_final_image(out, expected_size=(1920, 1080))
    assert ok is False
    assert any("resolution" in r for r in reasons)


def test_validate_rejects_tiny_file(tmp_path):
    tiny = tmp_path / "tiny.jpg"
    tiny.write_bytes(b"not a real image")
    ok, reasons, _ = validate_final_image(tiny, min_bytes=20_000)
    assert ok is False
    assert any("too small" in r for r in reasons)


def test_validate_missing_sidecar(tmp_path):
    src = _source(tmp_path / "src.jpg")
    out = tmp_path / "good.jpg"
    assert compose_quote_image(src, QUOTE, output_path=out)["ok"] is True
    out.with_suffix(".json").unlink()

    ok, reasons, _ = validate_final_image(out, must_contain_quote=QUOTE)
    assert ok is False
    assert "no composition metadata" in reasons


def test_validate_rejects_flat_image(tmp_path):
    flat = tmp_path / "flat.jpg"
    Image.new("RGB", (1080, 1920), (30, 30, 30)).save(flat, quality=95)
    ok, reasons, _ = validate_final_image(flat, min_bytes=0)
    assert ok is False
    assert any("flat" in r for r in reasons)


def test_validate_wrong_quote_in_sidecar(tmp_path):
    src = _source(tmp_path / "src.jpg")
    out = tmp_path / "good.jpg"
    assert compose_quote_image(src, QUOTE, output_path=out)["ok"] is True

    ok, reasons, _ = validate_final_image(out, must_contain_quote="A totally different line here")
    assert ok is False
    assert any("composition metadata" in r for r in reasons)
