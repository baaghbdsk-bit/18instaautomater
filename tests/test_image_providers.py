"""Tests for the swappable image providers. NO real network calls are made."""

import base64
import io
import json
import os
from pathlib import Path

import pytest
import requests
from PIL import Image

import config
import net
from image_providers import (
    ImageProvider,
    ImageRequest,
    ImageResult,
    available_providers,
    get_provider,
)
from image_providers import nvidia, perchance, placeholder


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code=200, content=b"", json_data=None, text=""):
        self.status_code = status_code
        self.content = content
        self.text = text
        self._json = json_data if json_data is not None else {}

    def json(self):
        return self._json


def _valid_png(width=120, height=120) -> bytes:
    """A real, decodable PNG comfortably larger than the 10 KB floor."""
    image = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _mock_http(monkeypatch, get_responses=None, post_responses=None):
    """Patch requests.get/post with scripted FakeResponses; return call logs."""
    calls = {"get": [], "post": []}
    gets = list(get_responses if get_responses is not None
                else [FakeResponse(200, json_data={"ready": True})])
    posts = list(post_responses if post_responses is not None
                 else [FakeResponse(200, content=_valid_png())])

    def fake_get(url, **kwargs):
        calls["get"].append((url, kwargs))
        return gets[min(len(calls["get"]) - 1, len(gets) - 1)]

    def fake_post(url, **kwargs):
        calls["post"].append((url, kwargs))
        return posts[min(len(calls["post"]) - 1, len(posts) - 1)]

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    return calls


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Sandbox all configuration and remove retry backoff sleeps."""
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path / "images")
    monkeypatch.setattr(config, "TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(config, "PERCHANCE_URL", "http://127.0.0.1:8000")
    monkeypatch.setattr(config, "PERCHANCE_STYLE", "Cinematic")
    monkeypatch.setattr(config, "PERCHANCE_ASPECT", "512x768")
    monkeypatch.setattr(config, "PERCHANCE_GUIDANCE", 7.0)
    monkeypatch.setattr(config, "PERCHANCE_NEGATIVE", "nude, explicit")
    monkeypatch.setattr(config, "PERCHANCE_TIMEOUT", 240)
    monkeypatch.setattr(config, "PERCHANCE_RETRIES", 2)
    monkeypatch.setattr(config, "IMAGE_PROVIDER", "perchance")
    monkeypatch.setattr(config, "ALLOW_PLACEHOLDER", False)
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(
        config, "NVIDIA_FLUX_URL",
        "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell",
    )
    monkeypatch.setattr(config, "NVIDIA_TIMEOUT", 300)

    # Keep net.with_retry's real classification/attempt logic, just drop sleeps.
    def fast_retry(fn, *, attempts=4, base_ms=1200, label="call",
                   is_retryable=None, sleep_fn=None):
        return net.with_retry(
            fn, attempts=attempts, base_ms=1, label=label,
            is_retryable=is_retryable, sleep_fn=lambda _seconds: None,
        )

    monkeypatch.setattr(perchance, "with_retry", fast_retry)
    monkeypatch.setattr(nvidia, "with_retry", fast_retry)
    yield


# ---------------------------------------------------------------------------
# base contracts
# ---------------------------------------------------------------------------
def test_dataclass_defaults():
    request = ImageRequest(prompt="hello")
    assert request.negative_prompt == ""
    assert request.aspect_ratio == "512x768"
    assert request.reference_images == []
    assert request.metadata == {}
    result = ImageResult(ok=True, status="generated")
    assert result.status in {"generated", "failed", "unsupported", "skipped"}
    assert isinstance(placeholder.PlaceholderProvider(), ImageProvider)


# ---------------------------------------------------------------------------
# Perchance
# ---------------------------------------------------------------------------
def test_payload_matches_verified_api_exactly(monkeypatch):
    calls = _mock_http(monkeypatch,
                       post_responses=[FakeResponse(200, content=_valid_png())])
    request = ImageRequest(prompt="a neon city", seed="12345")

    result = perchance.PerchanceProvider().generate(request)

    assert result.ok is True
    assert len(calls["post"]) == 1
    url, kwargs = calls["post"][0]
    assert url == "http://127.0.0.1:8000/api/v1/generate/raw"
    assert kwargs["timeout"] == config.PERCHANCE_TIMEOUT
    assert kwargs["json"] == {
        "prompt": "a neon city",
        "negative_prompt": "nude, explicit",
        "aspect_ratio": "512x768",
        "style": "Cinematic",
        "style_mix": "Not Mix",
        "guidance_scale": 7.0,
        "seed": "12345",
        "num_images": 1,
    }, "payload must contain exactly the verified native fields"


def test_health_gate_blocks_generation(monkeypatch):
    calls = _mock_http(
        monkeypatch,
        get_responses=[FakeResponse(200, json_data={"ready": False})],
        post_responses=[],
    )

    result = perchance.PerchanceProvider().generate(ImageRequest(prompt="x"))

    assert result.ok is False
    assert result.status == "failed"
    assert "not ready" in result.error
    assert calls["post"] == [], "no generation may run when health is false"


def test_health_rejects_http_error_and_non_json(monkeypatch):
    calls = _mock_http(monkeypatch,
                       get_responses=[FakeResponse(503, text="warming up")])
    provider = perchance.PerchanceProvider()
    assert provider.health() is False
    assert "timeout" in calls["get"][0][1]  # short health timeout

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(
        200, json_data={"ready": True}))
    assert provider.health() is True


def test_retry_on_503(monkeypatch):
    png = _valid_png()
    calls = _mock_http(monkeypatch, post_responses=[
        FakeResponse(503, text="busy"), FakeResponse(200, content=png),
    ])

    result = perchance.PerchanceProvider().generate(ImageRequest(prompt="x"))

    assert result.ok is True
    assert result.status == "generated"
    assert len(calls["post"]) == 2, "503 is retryable"


def test_no_retry_on_400(monkeypatch):
    calls = _mock_http(monkeypatch, post_responses=[
        FakeResponse(400, text="bad prompt"),
    ])

    result = perchance.PerchanceProvider().generate(ImageRequest(prompt="x"))

    assert result.ok is False
    assert result.status == "failed"
    assert "400" in result.error
    assert len(calls["post"]) == 1, "400 is a validation error — never retry"


def test_no_retry_on_500(monkeypatch):
    calls = _mock_http(monkeypatch, post_responses=[
        FakeResponse(500, text="engine failure"),
    ])

    result = perchance.PerchanceProvider().generate(ImageRequest(prompt="x"))

    assert result.ok is False
    assert len(calls["post"]) == 1, "500 is non-retryable in this provider"


def test_tiny_response_rejected(monkeypatch):
    tiny = Image.new("RGB", (8, 8), (1, 2, 3))
    buf = io.BytesIO()
    tiny.save(buf, format="PNG")
    _mock_http(monkeypatch, post_responses=[FakeResponse(200, content=buf.getvalue())])

    result = perchance.PerchanceProvider().generate(ImageRequest(prompt="x"))

    assert result.ok is False
    assert result.status == "failed"
    assert "too little data" in result.error
    assert not list(Path(config.IMAGES_DIR).glob("*"))


def test_invalid_response_rejected(monkeypatch):
    _mock_http(monkeypatch, post_responses=[
        FakeResponse(200, content=b"this is not an image " * 2000),
    ])

    result = perchance.PerchanceProvider().generate(ImageRequest(prompt="x"))

    assert result.ok is False
    assert "invalid image data" in result.error


def test_empty_prompt_rejected(monkeypatch):
    calls = _mock_http(monkeypatch, post_responses=[])
    result = perchance.PerchanceProvider().generate(ImageRequest(prompt="   "))
    assert result.ok is False
    assert "non-empty" in result.error
    assert calls["post"] == []


def test_saved_image_and_metadata(monkeypatch):
    png = _valid_png()
    _mock_http(monkeypatch, post_responses=[FakeResponse(200, content=png)])
    request = ImageRequest(prompt="sunset", negative_prompt="blurry",
                           seed="42", num_images=1)

    result = perchance.PerchanceProvider().generate(request)

    assert result.ok is True
    assert result.status == "generated"
    assert result.provider == "perchance"
    assert result.model == "perchance-image"
    assert result.seed == "42"
    assert Path(result.path).exists()
    assert Path(result.path).read_bytes() == png
    meta = result.metadata
    for key in ("prompt", "negative_prompt", "aspect_ratio", "style",
                "guidance_scale", "num_images", "duration", "bytes",
                "reference_images_supported"):
        assert key in meta
    assert meta["negative_prompt"] == "blurry"
    assert meta["num_images"] == 1
    assert meta["bytes"] == len(png)
    assert meta["reference_images_supported"] is False
    assert meta["duration"] >= 0


def test_reference_images_recorded_as_unsupported(monkeypatch):
    _mock_http(monkeypatch, post_responses=[FakeResponse(200, content=_valid_png())])
    request = ImageRequest(prompt="x", reference_images=["/tmp/ref.png"])

    result = perchance.PerchanceProvider().generate(request)

    assert result.ok is True  # generation still succeeds
    assert result.metadata["reference_images_supported"] is False
    assert "warning" in result.metadata
    assert "no reference-image parameter" in result.metadata["warning"]


# ---------------------------------------------------------------------------
# Placeholder
# ---------------------------------------------------------------------------
def test_placeholder_refuses_when_disabled():
    result = placeholder.PlaceholderProvider().generate(
        ImageRequest(prompt="x", width=64, height=64)
    )
    assert result.ok is False
    assert result.status == "unsupported"
    assert "forbidden in production" in result.error
    assert result.metadata["is_placeholder"] is True


def test_placeholder_generates_when_allowed():
    config.ALLOW_PLACEHOLDER = True
    result = placeholder.PlaceholderProvider().generate(
        ImageRequest(prompt="x", width=64, height=64)
    )
    assert result.ok is True
    assert result.status == "generated"
    assert result.metadata["is_placeholder"] is True
    assert Path(result.path).exists()
    with Image.open(result.path) as image:
        assert image.size == (64, 64)


# ---------------------------------------------------------------------------
# NVIDIA
# ---------------------------------------------------------------------------
def test_nvidia_without_key_is_unsupported(monkeypatch):
    calls = _mock_http(monkeypatch, post_responses=[])
    result = nvidia.NvidiaProvider().generate(ImageRequest(prompt="x"))
    assert result.ok is False
    assert result.status == "unsupported"
    assert "NVIDIA_API_KEY" in result.error
    assert calls["post"] == []


def test_nvidia_generation_payload_and_result(monkeypatch):
    config.NVIDIA_API_KEY = "nvapi-test"
    png = _valid_png(80, 80)
    encoded = base64.b64encode(png).decode("ascii")
    body = json.dumps({"artifacts": [{"base64": encoded}]}).encode("utf-8")
    calls = _mock_http(monkeypatch, post_responses=[
        FakeResponse(200, content=body),
    ])

    result = nvidia.NvidiaProvider().generate(
        ImageRequest(prompt="a comet", width=768, height=512, seed="99",
                     reference_images=["ref.png"])
    )

    assert result.ok is True
    assert result.status == "generated"
    assert result.model == "flux.1-schnell"
    assert result.provider == "nvidia"
    assert Path(result.path).exists()
    assert Path(result.path).read_bytes() == png

    url, kwargs = calls["post"][0]
    assert url == config.NVIDIA_FLUX_URL
    assert kwargs["headers"]["Authorization"] == "Bearer nvapi-test"
    assert kwargs["timeout"] == config.NVIDIA_TIMEOUT
    assert kwargs["json"] == {
        "prompt": "a comet",
        "mode": "base",
        "cfg_scale": 0,
        "width": 768,
        "height": 512,
        "seed": 99,
        "steps": 4,
    }
    assert result.metadata["reference_images_supported"] is False
    assert "warning" in result.metadata


# ---------------------------------------------------------------------------
# Registry / exports
# ---------------------------------------------------------------------------
def test_registry_unknown_name_raises():
    with pytest.raises(ValueError) as excinfo:
        get_provider("does-not-exist")
    message = str(excinfo.value)
    for name in ("perchance", "placeholder", "nvidia"):
        assert name in message


def test_registry_defaults_to_configured_provider():
    assert isinstance(get_provider(), perchance.PerchanceProvider)
    assert isinstance(get_provider("NVIDIA"), nvidia.NvidiaProvider)
    assert isinstance(get_provider("placeholder"), placeholder.PlaceholderProvider)
    assert available_providers() == ["fal_kontext", "nvidia", "perchance", "placeholder"]
