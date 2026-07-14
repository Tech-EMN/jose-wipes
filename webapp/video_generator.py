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

    Currently only Higgsfield is supported. When new providers
    are added, this is the single place to swap implementations.
    """
    return HiggsfieldVideoGenerator(
        application=application,
        extra_arguments=extra_arguments,
    )
