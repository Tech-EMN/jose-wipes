"""Tests for F4: Abstract VideoGenerator interface."""

from __future__ import annotations

import subprocess
import sys
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts.gerador_midia import gerar_video_higgsfield
from scripts.integration_errors import IntegrationFailure
from webapp.video_generator import (
    VideoGenerator,
    VideoGenerationRequest,
    VideoGenerationResult,
    HiggsfieldVideoGenerator,
    OpenAISoraVideoGenerator,
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
        monkeypatch.setenv("HF_API_KEY", "")
        monkeypatch.setenv("HF_API_SECRET", "")
        import importlib
        import scripts.config as cfg
        importlib.reload(cfg)
        gen = HiggsfieldVideoGenerator("test-app")
        assert gen.health_check() is False

    def test_polling_network_error_reuses_submitted_request(self, tmp_path):
        class Completed:
            pass

        class Failed:
            pass

        class NSFW:
            pass

        class Cancelled:
            pass

        class InProgress:
            pass

        controller = SimpleNamespace(request_id="request-1")
        client = SimpleNamespace(
            Completed=Completed,
            Failed=Failed,
            NSFW=NSFW,
            Cancelled=Cancelled,
            submit=MagicMock(return_value=controller),
            status=MagicMock(
                side_effect=[
                    OSError("network is unreachable"),
                    InProgress(),
                    Completed(),
                ]
            ),
            result=MagicMock(
                return_value={"video": {"url": "https://example.com/video.mp4"}}
            ),
        )
        output_path = tmp_path / "video.mp4"

        def download(command, **_kwargs):
            Path(command[command.index("-o") + 1]).write_bytes(b"video")
            return subprocess.CompletedProcess(command, 0)

        with patch.dict(sys.modules, {"higgsfield_client": client}), patch(
            "scripts.gerador_midia._subprocess_run", side_effect=download
        ), patch(
            "scripts.gerador_midia._probe_video_dimensions",
            return_value=(1080, 1920),
        ), patch("scripts.gerador_midia.time.sleep"):
            result = gerar_video_higgsfield(
                "kling-video/v2.1/master/text-to-video",
                "A vertical commercial",
                output_path=output_path,
                max_retries=2,
                raise_on_failure=True,
            )

        assert result == output_path
        client.submit.assert_called_once()
        assert client.submit.call_args.kwargs["arguments"]["resolution"] == "1080p"
        assert client.status.call_count == 3
        client.result.assert_called_once_with("request-1")

    def test_rejects_non_native_1080p_provider_output(self, tmp_path):
        class Completed:
            pass

        class Failed:
            pass

        class NSFW:
            pass

        class Cancelled:
            pass

        client = SimpleNamespace(
            Completed=Completed,
            Failed=Failed,
            NSFW=NSFW,
            Cancelled=Cancelled,
            submit=MagicMock(return_value=SimpleNamespace(request_id="request-1")),
            status=MagicMock(return_value=Completed()),
            result=MagicMock(
                return_value={"video": {"url": "https://example.com/video.mp4"}}
            ),
        )
        output_path = tmp_path / "video.mp4"

        def download(command, **_kwargs):
            Path(command[command.index("-o") + 1]).write_bytes(b"video")
            return subprocess.CompletedProcess(command, 0)

        with patch.dict(sys.modules, {"higgsfield_client": client}), patch(
            "scripts.gerador_midia._subprocess_run",
            side_effect=download,
        ), patch(
            "scripts.gerador_midia._probe_video_dimensions",
            return_value=(720, 1280),
        ), pytest.raises(IntegrationFailure) as captured:
            gerar_video_higgsfield(
                "kling-video/v2.1/master/text-to-video",
                "A vertical commercial",
                resolucao="1080p",
                output_path=output_path,
                max_retries=0,
                raise_on_failure=True,
            )

        assert captured.value.code == "native_resolution_mismatch"
        assert not output_path.exists()


class TestOpenAISoraVideoGenerator:
    def test_sora_pro_requests_native_vertical_1080p(self, tmp_path):
        output_path = tmp_path / "video.mp4"
        client = MagicMock()
        client.videos.create_and_poll.return_value.id = "video-id"
        client.videos.download_content.return_value.write_to_file.side_effect = (
            lambda path: Path(path).write_bytes(b"video")
        )

        with patch("scripts.config.OPENAI_API_KEY", "test-key"), patch(
            "openai.OpenAI", return_value=client
        ):
            OpenAISoraVideoGenerator("sora-2-pro").generate(
                VideoGenerationRequest(
                    prompt="test prompt",
                    aspect_ratio="9:16",
                    resolution="1080p",
                    duration_seconds=4,
                    output_path=output_path,
                )
            )

        assert client.videos.create_and_poll.call_args.kwargs["size"] == "1080x1920"

    def test_uses_local_reference_and_writes_download(self, tmp_path):
        reference_path = tmp_path / "reference.png"
        reference_path.write_bytes(b"image")
        output_path = tmp_path / "video.mp4"
        client = MagicMock()
        client.videos.create_and_poll.return_value.id = "video-id"
        client.videos.download_content.return_value.write_to_file.side_effect = (
            lambda path: Path(path).write_bytes(b"video")
        )

        with patch("scripts.config.OPENAI_API_KEY", "test-key"), patch(
            "openai.OpenAI", return_value=client
        ), patch(
            "webapp.video_generator._prepare_sora_reference",
            return_value=reference_path,
        ):
            result = OpenAISoraVideoGenerator("sora-2").generate(
                VideoGenerationRequest(
                    prompt="test prompt",
                    aspect_ratio="9:16",
                    resolution="720p",
                    duration_seconds=5,
                    output_path=output_path,
                    reference_image_path=reference_path,
                )
            )

        assert result.output_path.read_bytes() == b"video"
        assert client.videos.create_and_poll.call_args.kwargs["seconds"] == "4"
        assert client.videos.create_and_poll.call_args.kwargs["input_reference"] == reference_path
        client.videos.download_content.return_value.write_to_file.assert_called_once_with(output_path)

    def test_reports_moderation_failure_before_download(self, tmp_path):
        client = MagicMock()
        video = client.videos.create_and_poll.return_value
        video.id = "video-id"
        video.status = "failed"
        video.error.code = "moderation_blocked"
        video.error.message = "Your request was blocked by our moderation system."

        with patch("scripts.config.OPENAI_API_KEY", "test-key"), patch(
            "openai.OpenAI", return_value=client
        ), pytest.raises(IntegrationFailure) as captured:
            OpenAISoraVideoGenerator("sora-2").generate(
                VideoGenerationRequest(
                    prompt="neutral studio background",
                    aspect_ratio="9:16",
                    resolution="720p",
                    duration_seconds=5,
                    output_path=tmp_path / "video.mp4",
                )
            )

        assert captured.value.code == "sora_moderation_blocked"
        assert captured.value.retryable is False
        assert captured.value.submit_confirmed is True
        assert captured.value.render_confirmed is False
        client.videos.download_content.assert_not_called()


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
