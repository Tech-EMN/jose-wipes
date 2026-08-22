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


def _prepare_sora_reference(
    source_path: Path,
    output_path: Path,
    size: str,
) -> Path:
    from scripts.compositor import _subprocess_run

    width, height = size.split("x", 1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = _subprocess_run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-vf",
            (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=white"
            ),
            "-frames:v",
            "1",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(result.stderr.strip() or "FFmpeg failed to prepare Sora reference.")
    return output_path


@dataclass(frozen=True)
class VideoGenerationRequest:
    """Input parameters for a video generation call."""

    prompt: str
    aspect_ratio: str  # e.g. "9:16", "16:9"
    resolution: str  # e.g. "720p", "1080p"
    duration_seconds: int
    output_path: Path
    reference_image_url: str | None = None
    reference_image_path: Path | None = None
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

    # sora-2 só suporta 720x1280 / 1280x720
    # sora-2-pro suporta todas: 720x1280, 1280x720, 1080x1920, 1920x1080
    SORA_SIZES_PRO: dict[tuple[str, str], str] = {
        ("9:16", "720p"): "720x1280",
        ("9:16", "1080p"): "1080x1920",
        ("16:9", "720p"): "1280x720",
        ("16:9", "1080p"): "1920x1080",
    }
    SORA_SIZES_BASE: dict[tuple[str, str], str] = {
        ("9:16", "720p"): "720x1280",
        ("9:16", "1080p"): "720x1280",  # downgrade: sora-2 não tem 1080p
        ("16:9", "720p"): "1280x720",
        ("16:9", "1080p"): "1280x720",  # downgrade
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

        size_map = (
            self.SORA_SIZES_PRO
            if "pro" in self._model
            else self.SORA_SIZES_BASE
        )
        size = size_map.get(
            (request.aspect_ratio, request.resolution),
            "720x1280",
        )

        if "pro" not in self._model and request.resolution == "1080p":
            _log.warning(
                "Sora-2 não suporta 1080p; downgrade para 720p. "
                "Use Sora-2-Pro para resoluções acima de 720p.",
            )

        dur = request.duration_seconds
        nearest = min(self.SORA_DURATIONS, key=lambda x: (abs(x - dur), x))
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

        if request.reference_image_path:
            reference_path = request.output_path.with_name(
                f"{request.output_path.stem}_sora_reference.png"
            )
            try:
                params["input_reference"] = _prepare_sora_reference(
                    request.reference_image_path,
                    reference_path,
                    size,
                )
            except Exception as exc:
                raise IntegrationFailure(
                    service="openai",
                    stage="generation",
                    code="sora_reference_error",
                    user_message="Falha ao preparar a imagem de referência para a Sora.",
                    technical_message=str(exc),
                    retryable=False,
                ) from exc

        params.update(self._extra_arguments)

        try:
            video = client.videos.create_and_poll(**params)  # type: ignore[arg-type]
        except Exception as exc:
            from scripts.openai_utils import classify_openai_exception

            error_msg = str(exc)
            error_lower = error_msg.lower()
            classified = classify_openai_exception(exc, stage="generation")

            if classified.code == "insufficient_quota":
                raise classified from exc

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

        if getattr(video, "status", None) == "failed":
            error = getattr(video, "error", None)
            error_code = (
                error.get("code")
                if isinstance(error, dict)
                else getattr(error, "code", None)
            ) or "generation_failed"
            error_message = (
                error.get("message")
                if isinstance(error, dict)
                else getattr(error, "message", None)
            ) or "Video generation failed."
            moderation_blocked = error_code == "moderation_blocked"
            raise IntegrationFailure(
                service="openai",
                stage="generation",
                code=f"sora_{error_code}",
                user_message=(
                    "A Sora bloqueou o prompt pela moderação. Ajuste o briefing e tente novamente."
                    if moderation_blocked
                    else "A Sora não conseguiu concluir a geração do vídeo."
                ),
                technical_message=f"{error_code}: {error_message}",
                retryable=not moderation_blocked,
                submit_confirmed=True,
                render_confirmed=False,
                reason=str(error_code),
            )

        try:
            content = client.videos.download_content(video.id)
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            content.write_to_file(request.output_path)
        except Exception as exc:
            raise IntegrationFailure(
                service="openai",
                stage="generation",
                code="sora_download_error",
                user_message="Vídeo gerado mas falha no download.",
                technical_message=str(exc),
                retryable=True,
            ) from exc

        _log.info(
            "Sora: vídeo %s salvo em %s (%.1f MB)",
            video.id,
            request.output_path,
            request.output_path.stat().st_size / (1024 * 1024),
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
