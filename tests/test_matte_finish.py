"""Deterministic matte finish reduces specular highlights."""

from pathlib import Path

from PIL import Image

import matte_finish


def test_matte_finish_compresses_bright_pixels(tmp_path):
    src = tmp_path / "src.jpg"
    img = Image.new("RGB", (40, 40), (250, 250, 250))
    img.save(src)
    out = matte_finish.apply_matte_finish(src)
    assert Path(out).exists()
    result = Image.open(out).convert("RGB")
    # 250 -> 168 + (250-168)*0.55 ~= 213, plus tiny grain.
    assert max(result.getpixel((20, 20))) < 230


def test_matte_finish_keeps_midtones(tmp_path):
    src = tmp_path / "src.jpg"
    Image.new("RGB", (30, 30), (100, 100, 100)).save(src)
    out = matte_finish.apply_matte_finish(src)
    value = Image.open(out).convert("RGB").getpixel((15, 15))[0]
    assert 90 <= value <= 110
