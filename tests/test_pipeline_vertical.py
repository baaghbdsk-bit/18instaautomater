"""Pipeline orchestration tests: quote claim, prompt build, image dry-run.

All external services are mocked. No real generation request, no real Instagram
post, and no writes to the production database occur here.
"""

from pathlib import Path

import pytest
from PIL import Image

import db
import pipeline
from image_providers.base import ImageResult


class _Quote:
    id = "q-test"
    text = "You paused for a reason and we both know it"
    mood = "flirty"
    tags = []


class _FakeProvider:
    name = "perchance"

    def __init__(self, path: Path, fail: bool = False):
        self.path = path
        self.fail = fail
        self.request = None

    def generate(self, request):
        self.request = request
        if self.fail:
            return ImageResult(ok=False, provider=self.name, status="failed",
                               error="simulated provider failure")
        Image.new("RGB", (900, 1200), (40, 30, 60)).save(self.path)
        return ImageResult(
            ok=True, path=str(self.path), provider=self.name,
            model="perchance-image", seed=request.seed, status="generated",
            metadata={"attempts": 1, "is_placeholder": False})


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "engine.db")
    monkeypatch.setattr(pipeline, "KILL_SWITCH", False)
    monkeypatch.setattr(pipeline, "DRY_RUN", False)
    monkeypatch.setattr(pipeline, "login_account", lambda a: (_ for _ in ()).throw(
        RuntimeError("accounts disabled in tests")))
    monkeypatch.setattr(pipeline, "logout_all", lambda clients: None)
    monkeypatch.setattr(pipeline, "reconcile_stale", lambda clients: 0)
    monkeypatch.setattr(pipeline, "collect_insights", lambda clients: 0)
    monkeypatch.setattr(pipeline, "_character_seed", lambda: 123456)
    return tmp_path


def test_select_quote_claims_unused(isolated, monkeypatch):
    # Use two distinct simple quotes instead of relying on the class default.
    q1 = _Quote()
    q2 = _Quote()
    q2.id, q2.text = "q-test-2", "A completely different approved line here"
    monkeypatch.setattr(pipeline.quote_bank, "load_bank", lambda: [q1, q2])
    monkeypatch.setattr(pipeline.quote_bank, "select_unused",
                        lambda bank, used, rng=None: q2)
    claimed = []
    monkeypatch.setattr(db, "claim_quote", lambda qid, pid: claimed.append((qid, pid)) or True)
    monkeypatch.setattr(db, "used_quote_ids", lambda: set())

    pid = db.insert_post(account="test", status="pending")
    quote, _ = pipeline._select_quote(pid)
    assert quote.id == "q-test-2"
    assert claimed == [("q-test-2", pid)]


def test_select_quote_raises_when_bank_exhausted(isolated, monkeypatch):
    monkeypatch.setattr(pipeline.quote_bank, "load_bank", lambda: [_Quote()])
    monkeypatch.setattr(pipeline.quote_bank, "select_unused",
                        lambda bank, used, rng=None: None)
    monkeypatch.setattr(db, "used_quote_ids", lambda: {"q-test"})
    pid = db.insert_post(account="test", status="pending")
    with pytest.raises(RuntimeError, match="exhausted"):
        pipeline._select_quote(pid)


def test_build_request_preserves_identity(isolated):
    variation = pipeline.get_variation(pipeline.variation_keys()[0])
    request = pipeline._build_generation_request(_Quote(), variation, 99)
    assert pipeline.MASTER_PROFILE.identity_prompt() in request.prompt
    assert request.seed == "99"
    assert request.metadata["quote_id"] == "q-test"
    assert request.metadata["variation"] == variation.key
    assert request.num_images == 1


def test_dry_run_generates_composes_validates_and_records(isolated, monkeypatch):
    raw = isolated / "raw.jpg"
    provider = _FakeProvider(raw)

    monkeypatch.setattr(pipeline.quote_bank, "load_bank", lambda: [_Quote()])
    monkeypatch.setattr(pipeline.quote_bank, "select_unused",
                        lambda bank, used, rng=None: bank[0])
    monkeypatch.setattr(pipeline.quote_bank, "is_low",
                        lambda *a, **kw: False)
    monkeypatch.setattr(pipeline, "get_provider", lambda: provider)
    monkeypatch.setattr(
        pipeline, "compose_quote_image",
        lambda src, quote, output_path=None, variant="lower", handle="": {
            "ok": True,
            "path": str(isolated / "final.jpg"),
            "width": 1080, "height": 1920, "bytes": 60000,
            "variant": variant, "lines": [quote], "font_size": 100,
            "source": str(src), "is_placeholder": False, "sha256": "abc",
        })
    monkeypatch.setattr(
        pipeline, "validate_final_image",
        lambda path, must_contain_quote=None: (
            True, [], {"width": 1080, "height": 1920, "bytes": 60000}))
    monkeypatch.setattr(pipeline, "build_caption",
                        lambda *a, **kw: "caption from test", raising=False)

    rc = pipeline.run(["--dry-run", "--strict", "--mode", "photo"])
    assert rc == 0
    posts = db.recent_posts(1)
    assert posts, "a post row must be recorded"
    post = posts[0]
    assert str(post["quote_id"]).startswith("q")
    assert post["quote_text"]
    assert post["prompt_text"]
    assert post["generation_path"].endswith(".jpg")
    assert Path(post["generation_path"]).exists()
    assert post["final_image_path"].endswith("final.jpg")
    assert post["status"] in ("dry-run", "ready_to_publish")
    assert provider.request is not None
    assert pipeline.MASTER_PROFILE.identity_prompt() in provider.request.prompt
    assert db.quote_already_used(post["quote_id"])


def test_provider_failure_aborts_before_composition(isolated, monkeypatch):
    provider = _FakeProvider(isolated / "none.jpg", fail=True)
    monkeypatch.setattr(pipeline.quote_bank, "load_bank", lambda: [_Quote()])
    monkeypatch.setattr(pipeline.quote_bank, "select_unused",
                        lambda bank, used, rng=None: bank[0])
    monkeypatch.setattr(pipeline.quote_bank, "is_low",
                        lambda *a, **kw: False)
    monkeypatch.setattr(pipeline, "get_provider", lambda: provider)
    called = []
    monkeypatch.setattr(pipeline, "compose_quote_image",
                        lambda *a, **kw: called.append(True) or {"ok": True})
    rc = pipeline.run(["--dry-run", "--mode", "photo"])
    assert rc != 0
    assert not called, "composition must not run after a failed generation"
    post = db.recent_posts(1)[0]
    assert post["status"] == "failed"
    assert post["error_stage"] == "pipeline"


def test_reel_mode_renders_video_and_records_it(isolated, monkeypatch):
    raw = isolated / "raw.jpg"
    provider = _FakeProvider(raw)
    monkeypatch.setattr(pipeline.quote_bank, "load_bank", lambda: [_Quote()])
    monkeypatch.setattr(pipeline.quote_bank, "select_unused",
                        lambda bank, used, rng=None: bank[0])
    monkeypatch.setattr(pipeline.quote_bank, "is_low", lambda *a, **kw: False)
    monkeypatch.setattr(pipeline, "get_provider", lambda: provider)
    monkeypatch.setattr(pipeline, "MUSIC_ENABLED", False)
    monkeypatch.setattr(
        pipeline, "compose_quote_image",
        lambda src, quote, output_path=None, variant="lower", handle="": {
            "ok": True, "path": str(isolated / "final.jpg"),
            "width": 1080, "height": 1920, "bytes": 60000,
            "variant": variant, "lines": [quote], "font_size": 100,
            "source": str(src), "is_placeholder": False, "sha256": "abc"})
    monkeypatch.setattr(
        pipeline, "validate_final_image",
        lambda path, must_contain_quote=None: (
            True, [], {"width": 1080, "height": 1920, "bytes": 60000}))

    calls = []

    def fake_still_video(image, output, **kwargs):
        calls.append((image, output))
        return {"path": str(output), "duration": 12.0, "motion": "push_center",
                "size_bytes": 100000}

    monkeypatch.setattr(pipeline, "still_video", fake_still_video)
    monkeypatch.setattr(pipeline, "validate_video",
                        lambda path, **kwargs: (True, [], {"duration": 12.0,
                                                           "bytes": 100000}))

    rc = pipeline.run(["--dry-run", "--strict"])
    assert rc == 0
    assert len(calls) == 1
    post = db.recent_posts(1)[0]
    assert post["output_kind"] == "reel"
    assert post["video_path"].endswith(".mp4")
    assert post["final_image_path"].endswith(".jpg")
