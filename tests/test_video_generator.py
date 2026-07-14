"""Tests for F4: Abstract VideoGenerator interface."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from webapp.video_generator import (
    VideoGenerator,
    VideoGenerationRequest,
    VideoGenerationResult,
    HiggsfieldVideoGenerator,
    create_video_generator,
)


class TestVideoGenerationRequest:
    def test_create_request(self):
        req = VideoGenerationRequest(
            prompt="test",
            aspect_ratio="9:16",
            resolution="720p",
            duration_seconds=10,
            output_path=Path("/tmp/test.mp4"),
        )
        assert req.prompt == "test"
        assert req.aspect_ratio == "9:16"
        assert req.duration_seconds == 10

    def test_optional_fields_default(self):
        req = VideoGenerationRequest(
            prompt="test",
            aspect_ratio="16:9",
            resolution="1080p",
            duration_seconds=5,
            output_path=Path("/tmp/out.mp4"),
        )
        assert req.reference_image_url is None
        assert req.seed is None

    def test_frozen_dataclass(self):
        req = VideoGenerationRequest(
            prompt="test",
            aspect_ratio="9:16",
            resolution="720p",
            duration_seconds=10,
            output_path=Path("/tmp/test.mp4"),
        )
        with pytest.raises(Exception):
            req.prompt = "changed"  # frozen


class TestHiggsfieldVideoGenerator:
    def test_provider_name(self):
        gen = HiggsfieldVideoGenerator("test-app")
        assert gen.provider_name == "Higgsfield"

    def test_health_check_with_keys(self, monkeypatch):
        monkeypatch.setenv("HF_API_KEY", "test-key")
        monkeypatch.setenv("HF_API_SECRET", "test-secret")
        import importlib
        import scripts.config as cfg
        importlib.reload(cfg)
        gen = HiggsfieldVideoGenerator("test-app")
        assert gen.health_check() is True

    def test_health_check_without_keys(self, monkeypatch):
        monkeypatch.delenv("HF_API_KEY", raising=False)
        monkeypatch.delenv("HF_API_SECRET", raising=False)
        import importlib
        import scripts.config as cfg
        importlib.reload(cfg)
        gen = HiggsfieldVideoGenerator("test-app")
        assert gen.health_check() is False


class TestCreateVideoGenerator:
    def test_factory_returns_higgsfield(self):
        gen = create_video_generator("bytedance/seedance/pro")
        assert isinstance(gen, HiggsfieldVideoGenerator)
        assert gen.provider_name == "Higgsfield"

    def test_factory_with_extra_args(self):
        gen = create_video_generator(
            "bytedance/seedance/pro",
            extra_arguments={"num_inference_steps": 50},
        )
        assert gen._extra_arguments == {"num_inference_steps": 50}


class TestVideoGeneratorWithMock:
    """Test that the interface works with a mock provider."""

    def test_mock_generator(self, tmp_path):
        """A mock VideoGenerator should satisfy the interface."""
        class MockGenerator(VideoGenerator):
            @property
            def provider_name(self):
                return "Mock"

            def generate(self, request):
                output = request.output_path
                output.write_text("fake video")
                return VideoGenerationResult(
                    output_path=output,
                    provider=self.provider_name,
                    duration_seconds=float(request.duration_seconds),
                )

            def health_check(self):
                return True

        gen = MockGenerator()
        req = VideoGenerationRequest(
            prompt="test",
            aspect_ratio="9:16",
            resolution="720p",
            duration_seconds=10,
            output_path=tmp_path / "test.mp4",
        )
        result = gen.generate(req)
        assert result.provider == "Mock"
        assert result.output_path.exists()
