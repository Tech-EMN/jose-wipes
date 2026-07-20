"""Abstract video generator interface for the José Wipes pipeline.

Decouples the video generation provider (Higgsfield) from the
pipeline orchestration, enabling provider swaps without refactoring
the entire codebase.

Usage:
    from webapp.video_generator import create_video_generator

    generator = create_video_generator()
    result = generator.generate(prompt, aspect_ratio="9:16", ...)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoGenerationRequest:
    """Input parameters for a video generation call."""

    prompt: str
    aspect_ratio: str  # e.g. "9:16", "16:9"
    resolution: str  # e.g. "720p", "1080p"
    duration_seconds: int
    output_path: Path
    reference_image_url: str | None = None
    seed: int | None = None


@dataclass(frozen=True)
class VideoGenerationResult:
    """Result of a successful video generation."""

    output_path: Path
    provider: str
    duration_seconds: float | None = None


class VideoGenerator(ABC):
    """Abstract base for video generation providers.

    Implementations must handle:
    - API authentication
    - Prompt submission
    - Download and save to output_path
    - Error handling with structured exceptions
    """

    @abstractmethod
    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """Generate a video from the given request.

        Args:
            request: Fully-specified generation parameters.

        Returns:
            VideoGenerationResult with the output path.

        Raises:
            IntegrationFailure: on provider-specific failures.
        """

    @abstractmethod
    def health_check(self) -> bool:
        """Verify the provider is reachable and authenticated.

        Returns True if the provider is ready to accept generation requests.
        """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier (e.g. 'Higgsfield')."""


class OpenAISoraVideoGenerator(VideoGenerator):
    """OpenAI Sora implementation of the VideoGenerator interface."""

    SORA_SIZES: dict[tuple[str, str], str] = {
        ("9:16", "720p"): "720x1280",
        ("9:16", "1080p"): "1024x1792",
        ("16:9", "720p"): "1280x720",
        ("16:9", "1080p"): "1792x1024",
    }

    SORA_DURATIONS: frozenset[int] = frozenset({4, 8, 12})

    def __init__(
        self,
        model: str,
        *,
        extra_arguments: dict | None = None,
    ) -> None:
        self._model = model
        self._extra_arguments = extra_arguments or {}

    @property
    def provider_name(self) -> str:
        return f"OpenAI Sora ({self._model})"

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        from openai import OpenAI

        from scripts.config import OPENAI_API_KEY
        from scripts.integration_errors import IntegrationFailure

        if not OPENAI_API_KEY:
            raise IntegrationFailure(
                service="openai",
                stage="generation",
                code="no_api_key",
                user_message="OPENAI_API_KEY não configurada no .env.",
                technical_message="Missing OPENAI_API_KEY for Sora generation.",
                retryable=False,
            )

        client = OpenAI(api_key=OPENAI_API_KEY)

        size = self.SORA_SIZES.get(
            (request.aspect_ratio, request.resolution),
            "720x1280",
        )

        dur = request.duration_seconds
        nearest = min(self.SORA_DURATIONS, key=lambda x: abs(x - dur))
        seconds = str(nearest)

        if nearest != dur:
            _log.info(
                "Sora: duração %ds arredondada para %ss (suportado: 4/8/12)",
                dur,
                seconds,
            )

        params: dict[str, object] = {
            "model": self._model,
            "prompt": request.prompt,
            "seconds": seconds,
            "size": size,
            "poll_interval_ms": 5000,
        }

        if request.reference_image_url:
            from openai.types.image_input_reference_param import (
                ImageInputReferenceParam,
            )

            params["input_reference"] = ImageInputReferenceParam(
                image_url=request.reference_image_url,
            )

        params.update(self._extra_arguments)

        try:
            video = client.videos.create_and_poll(**params)  # type: ignore[arg-type]
        except Exception as exc:
            error_msg = str(exc)
            error_lower = error_msg.lower()

            # Auth / permission errors are NOT retryable
            if "insufficient permissions" in error_lower or "401" in error_msg:
                raise IntegrationFailure(
                    service="openai",
                    stage="generation",
                    code="sora_auth_error",
                    user_message=(
                        "OPENAI_API_KEY sem permissão para Sora. "
                        "Adicione o scope 'api.videos.write' na API key "
                        "no dashboard da OpenAI."
                    ),
                    technical_message=error_msg,
                    retryable=False,
                ) from exc

            if "rate" in error_lower or "429" in error_msg:
                raise IntegrationFailure(
                    service="openai",
                    stage="generation",
                    code="sora_rate_limit",
                    user_message="Limite de requisições da Sora atingido. Aguarde e tente novamente.",
                    technical_message=error_msg,
                    retryable=True,
                ) from exc

            raise IntegrationFailure(
                service="openai",
                stage="generation",
                code="sora_api_error",
                user_message=f"Falha ao gerar vídeo via OpenAI Sora: {error_msg[:200]}",
                technical_message=error_msg,
                retryable=True,
            ) from exc

        try:
            content = client.videos.download_content(video.id)
        except Exception as exc:
            raise IntegrationFailure(
                service="openai",
                stage="generation",
                code="sora_download_error",
                user_message="Vídeo gerado mas falha no download.",
                technical_message=str(exc),
                retryable=True,
            ) from exc

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(content)

        _log.info(
            "Sora: vídeo %s salvo em %s (%.1f MB)",
            video.id,
            request.output_path,
            len(content) / (1024 * 1024),
        )

        return VideoGenerationResult(
            output_path=request.output_path,
            provider=self.provider_name,
            duration_seconds=float(seconds),
        )

    def health_check(self) -> bool:
        try:
            from scripts.config import OPENAI_API_KEY

            return bool(OPENAI_API_KEY)
        except Exception:
            return False


class HiggsfieldVideoGenerator(VideoGenerator):
    """Higgsfield API implementation of the VideoGenerator interface."""

    def __init__(self, application: str, *, extra_arguments: dict | None = None) -> None:
        self._application = application
        self._extra_arguments = extra_arguments or {}

    @property
    def provider_name(self) -> str:
        return "Higgsfield"

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        from scripts.gerador_midia import gerar_video_higgsfield

        result_path = gerar_video_higgsfield(
            self._application,
            request.prompt,
            aspecto=request.aspect_ratio,
            resolucao=request.resolution,
            duracao=request.duration_seconds,
            output_path=str(request.output_path),
            reference_image_url=request.reference_image_url,
            extra_arguments=self._extra_arguments,
            raise_on_failure=True,
            max_retries=0,
        )

        if not result_path:
            from scripts.integration_errors import IntegrationFailure
            raise IntegrationFailure(
                service="higgsfield",
                stage="generation",
                code="no_output",
                user_message="Falha ao gerar vídeo via Higgsfield.",
                technical_message="gerar_video_higgsfield returned None",
                retryable=True,
            )

        return VideoGenerationResult(
            output_path=Path(result_path),
            provider=self.provider_name,
        )

    def health_check(self) -> bool:
        try:
            from scripts.config import HF_API_KEY, HF_API_SECRET
            return bool(HF_API_KEY and HF_API_SECRET)
        except Exception:
            return False


def create_video_generator(
    application: str,
    *,
    extra_arguments: dict | None = None,
) -> VideoGenerator:
    """Factory: create the configured video generator.

    Routing:
    - "openai:<model>" → OpenAISoraVideoGenerator  (ex: "openai:sora-2")
    - anything else   → HiggsfieldVideoGenerator   (ex: "kling-video/v2.1/...")
    """
    if application.startswith("openai:"):
        model = application.split(":", 1)[1]
        return OpenAISoraVideoGenerator(
            model=model,
            extra_arguments=extra_arguments,
        )

    return HiggsfieldVideoGenerator(
        application=application,
        extra_arguments=extra_arguments,
    )
