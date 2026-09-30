"""Tests for F4: Abstract VideoGenerator interface."""

from __future__ import annotations

import subprocess
import sys
from contextlib import contextmanager
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts.gerador_midia import gerar_video_higgsfield
from scripts.higgsfield_api import HiggsfieldRequestStatus, HiggsfieldStatusSnapshot
from scripts.integration_errors import IntegrationFailure
from webapp.video_generator import (
    VideoGenerator,
    VideoGenerationRequest,
    VideoGenerationResult,
    HiggsfieldVideoGenerator,
    create_video_generator,
)


STATUS_URL = "https://api.higgsfield.ai/requests/request-1/status"
VIDEO_URL = "https://example.com/video.mp4"


def _snapshot(status: HiggsfieldRequestStatus, **payload: object) -> HiggsfieldStatusSnapshot:
    return HiggsfieldStatusSnapshot(status, status.value, {"status": status.value, **payload})


def _write_download(command, **_kwargs):
    Path(command[command.index("-o") + 1]).write_bytes(b"video")
    return subprocess.CompletedProcess(command, 0)


@contextmanager
def _higgsfield_environment(client, fetch_status, *, dimensions):
    with patch.dict(sys.modules, {"higgsfield_client": client}), patch(
        "scripts.gerador_midia.fetch_request_status", fetch_status
    ), patch(
        "scripts.gerador_midia._subprocess_run", side_effect=_write_download
    ), patch(
        "scripts.gerador_midia._probe_video_dimensions", return_value=dimensions
    ), patch("scripts.gerador_midia.time.sleep"):
        yield


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
        controller = SimpleNamespace(request_id="request-1", status_url=STATUS_URL)
        client = SimpleNamespace(submit=MagicMock(return_value=controller))
        fetch_status = MagicMock(
            side_effect=[
                OSError("network is unreachable"),
                _snapshot(HiggsfieldRequestStatus.IN_PROGRESS),
                _snapshot(HiggsfieldRequestStatus.COMPLETED, video={"url": VIDEO_URL}),
            ]
        )

        with _higgsfield_environment(client, fetch_status, dimensions=(1080, 1920)):
            result = gerar_video_higgsfield(
                "kling-video/v2.1/master/text-to-video",
                "A vertical commercial",
                output_path=tmp_path / "video.mp4",
                max_retries=2,
                raise_on_failure=True,
            )

        assert result == tmp_path / "video.mp4"
        client.submit.assert_called_once()
        assert client.submit.call_args.kwargs["arguments"]["resolution"] == "1080p"
        assert fetch_status.call_count == 3
        fetch_status.assert_called_with(STATUS_URL)

    def test_rejects_non_native_1080p_provider_output(self, tmp_path):
        client = SimpleNamespace(
            submit=MagicMock(
                return_value=SimpleNamespace(request_id="request-1", status_url=STATUS_URL)
            )
        )
        fetch_status = MagicMock(
            return_value=_snapshot(HiggsfieldRequestStatus.COMPLETED, video={"url": VIDEO_URL})
        )
        output_path = tmp_path / "video.mp4"

        with _higgsfield_environment(client, fetch_status, dimensions=(720, 1280)), pytest.raises(
            IntegrationFailure
        ) as captured:
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

    def test_failed_render_keeps_provider_reason(self, tmp_path):
        client = SimpleNamespace(
            submit=MagicMock(
                return_value=SimpleNamespace(request_id="request-1", status_url=STATUS_URL)
            )
        )
        fetch_status = MagicMock(
            return_value=_snapshot(
                HiggsfieldRequestStatus.FAILED,
                error="not_enough_credits",
            )
        )

        with _higgsfield_environment(client, fetch_status, dimensions=(1080, 1920)), pytest.raises(
            IntegrationFailure
        ) as captured:
            gerar_video_higgsfield(
                "kling-video/v2.1/master/text-to-video",
                "A vertical commercial",
                output_path=tmp_path / "video.mp4",
                max_retries=0,
                raise_on_failure=True,
            )

        assert captured.value.code == "insufficient_credits"
        assert captured.value.technical_message == "not_enough_credits"

    def test_unknown_status_keeps_polling_until_terminal(self, tmp_path):
        client = SimpleNamespace(
            submit=MagicMock(
                return_value=SimpleNamespace(request_id="request-1", status_url=STATUS_URL)
            )
        )
        fetch_status = MagicMock(
            side_effect=[
                HiggsfieldStatusSnapshot(HiggsfieldRequestStatus.UNKNOWN, "rendering"),
                _snapshot(HiggsfieldRequestStatus.COMPLETED, video={"url": VIDEO_URL}),
            ]
        )

        with _higgsfield_environment(client, fetch_status, dimensions=(1080, 1920)):
            result = gerar_video_higgsfield(
                "kling-video/v2.1/master/text-to-video",
                "A vertical commercial",
                output_path=tmp_path / "video.mp4",
                max_retries=0,
                raise_on_failure=True,
            )

        assert result == tmp_path / "video.mp4"
        assert fetch_status.call_count == 2


    @pytest.mark.parametrize(
        ("application", "expected_arguments"),
        [
            (
                "kling-video/v3.0/std/text-to-video",
                {"prompt": "A vertical commercial", "aspect_ratio": "9:16", "duration": 6, "sound": "off"},
            ),
            (
                "kling-video/v3.0/pro/text-to-video",
                {"prompt": "A vertical commercial", "aspect_ratio": "9:16", "duration": 6, "sound": "off"},
            ),
            (
                "alibaba/wan-3.0-prime/text-to-video",
                {
                    "prompt": "A vertical commercial",
                    "aspect_ratio": "9:16",
                    "duration": 6,
                    "generate_audio": False,
                    "resolution": "1080p",
                },
            ),
            (
                "higgsfield-ai/soul/v2/standard",
                {"prompt": "A vertical commercial", "aspect_ratio": "9:16", "resolution": "1080p"},
            ),
        ],
    )
    def test_profiled_models_receive_exactly_their_arguments(
        self, tmp_path, application, expected_arguments
    ):
        client = SimpleNamespace(
            submit=MagicMock(
                return_value=SimpleNamespace(request_id="request-1", status_url=STATUS_URL)
            )
        )
        fetch_status = MagicMock(
            return_value=_snapshot(HiggsfieldRequestStatus.COMPLETED, video={"url": VIDEO_URL})
        )

        with _higgsfield_environment(client, fetch_status, dimensions=(1080, 1920)):
            gerar_video_higgsfield(
                application,
                "A vertical commercial",
                output_path=tmp_path / "video.mp4",
                reference_image_url="https://example.com/product.png",
                max_retries=0,
                raise_on_failure=True,
            )

        assert client.submit.call_args.kwargs["application"] == application
        assert client.submit.call_args.kwargs["arguments"] == expected_arguments

    def test_kling_3_omits_arguments_the_model_does_not_accept(self, tmp_path):
        client = SimpleNamespace(
            submit=MagicMock(
                return_value=SimpleNamespace(request_id="request-1", status_url=STATUS_URL)
            )
        )
        fetch_status = MagicMock(
            return_value=_snapshot(HiggsfieldRequestStatus.COMPLETED, video={"url": VIDEO_URL})
        )

        with _higgsfield_environment(client, fetch_status, dimensions=(1080, 1920)):
            gerar_video_higgsfield(
                "kling-video/v3.0/pro/text-to-video",
                "A vertical commercial",
                output_path=tmp_path / "video.mp4",
                reference_image_url="https://example.com/product.png",
                max_retries=0,
                raise_on_failure=True,
            )

        arguments = client.submit.call_args.kwargs["arguments"]
        assert client.submit.call_args.kwargs["application"] == "kling-video/v3.0/pro/text-to-video"
        assert "resolution" not in arguments
        assert "reference_image_urls" not in arguments
        assert arguments["sound"] == "off"
        assert arguments["duration"] == 6


WAN_3_0_PRIME = "alibaba/wan-3.0-prime/text-to-video"


def _generate_wan(tmp_path, *, aspect_ratio, resolution, dimensions):
    client = SimpleNamespace(
        submit=MagicMock(
            return_value=SimpleNamespace(request_id="request-1", status_url=STATUS_URL)
        )
    )
    fetch_status = MagicMock(
        return_value=_snapshot(HiggsfieldRequestStatus.COMPLETED, video={"url": VIDEO_URL})
    )
    output_path = tmp_path / "video.mp4"

    with _higgsfield_environment(client, fetch_status, dimensions=dimensions):
        result = gerar_video_higgsfield(
            WAN_3_0_PRIME,
            "A vertical commercial",
            aspecto=aspect_ratio,
            resolucao=resolution,
            output_path=output_path,
            max_retries=0,
            raise_on_failure=True,
        )

    return client.submit.call_args.kwargs["arguments"], result, output_path


@pytest.mark.parametrize(
    ("aspect_ratio", "dimensions"),
    [("9:16", (1080, 1920)), ("16:9", (1920, 1080))],
)
def test_wan_native_1080p_output_is_accepted(tmp_path, aspect_ratio, dimensions):
    arguments, result, output_path = _generate_wan(
        tmp_path, aspect_ratio=aspect_ratio, resolution="1080p", dimensions=dimensions
    )

    assert arguments["resolution"] == "1080p"
    assert arguments["aspect_ratio"] == aspect_ratio
    assert result == output_path
    assert output_path.exists()


@pytest.mark.parametrize(
    ("aspect_ratio", "dimensions"),
    [("9:16", (720, 1280)), ("16:9", (1280, 720)), ("9:16", (1920, 1080))],
)
def test_wan_non_native_1080p_output_is_rejected(tmp_path, aspect_ratio, dimensions):
    with pytest.raises(IntegrationFailure) as captured:
        _generate_wan(
            tmp_path, aspect_ratio=aspect_ratio, resolution="1080p", dimensions=dimensions
        )

    assert captured.value.code == "native_resolution_mismatch"
    assert captured.value.retryable is False
    assert not (tmp_path / "video.mp4").exists()


def test_wan_720p_request_sends_720p_without_native_check(tmp_path):
    arguments, result, output_path = _generate_wan(
        tmp_path, aspect_ratio="9:16", resolution="720p", dimensions=(720, 1280)
    )

    assert arguments["resolution"] == "720p"
    assert result == output_path


def test_realistic_tier_defaults_to_kling_3_pro_without_native_sound(monkeypatch):
    import importlib
    import webapp.model_registry as registry
    from scripts.higgsfield_model_profiles import find_argument_profile

    monkeypatch.delenv("HF_MODEL_KLING_3_0", raising=False)
    config = importlib.reload(registry).get_model_config("kling_3_0")

    assert config.application == "kling-video/v3.0/pro/text-to-video"
    assert config.default_arguments == {}
    assert find_argument_profile(config.application).audio_off_arguments == {"sound": "off"}


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

    @pytest.mark.parametrize("application", ["openai:sora-2", "openai:sora-2-pro"])
    def test_factory_rejects_discontinued_sora(self, application):
        with pytest.raises(IntegrationFailure) as captured:
            create_video_generator(application)

        assert captured.value.code == "provider_discontinued"
        assert captured.value.retryable is False


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
