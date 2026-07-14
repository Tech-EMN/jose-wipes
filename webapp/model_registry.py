"""Registry of user-facing video models for the web studio."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from webapp.schemas import ResolutionLiteral, VideoModelLiteral


@dataclass(frozen=True)
class VideoModelConfig:
    """Configuration needed to render a job with a single Higgsfield model."""

    key: VideoModelLiteral
    label: str
    tier: str
    application: str
    allowed_resolutions: tuple[ResolutionLiteral, ...]
    default_arguments: dict[str, object] = field(default_factory=dict)
    fallback_application: str = ""
    fallback_note: str = ""


def _env_or_default(name: str, fallback: str) -> str:
    value = os.getenv(name, "").strip()
    return value or fallback


VIDEO_MODEL_REGISTRY: dict[VideoModelLiteral, VideoModelConfig] = {
    "seedance_1_5_pro": VideoModelConfig(
        key="seedance_1_5_pro",
        label="Seedance 1.5 Pro",
        tier="Padrão",
        application=_env_or_default(
            "HF_MODEL_SEEDANCE_1_5_PRO", "bytedance/seedance/pro"
        ),
        allowed_resolutions=("720p", "1080p"),
        fallback_application=_env_or_default(
            "HF_MODEL_SEEDANCE_1_5_PRO_FALLBACK",
            "bytedance/seedance/v1/pro/text-to-video",
        ),
        default_arguments={},
        fallback_note=(
            "Configure HF_MODEL_SEEDANCE_1_5_PRO no .env se a sua conta usar outro application ID."
        ),
    ),
    "kling_3_0": VideoModelConfig(
        key="kling_3_0",
        label="Kling 3.0",
        tier="Realista",
        application=_env_or_default(
            "HF_MODEL_KLING_3_0", "kling/3.0"
        ),
        allowed_resolutions=("720p", "1080p"),
        fallback_application=_env_or_default(
            "HF_MODEL_KLING_3_0_FALLBACK",
            "kling-video/v2.1/master/text-to-video",
        ),
        default_arguments={},
        fallback_note=(
            "Configure HF_MODEL_KLING_3_0 no .env se a sua conta usar outro application ID."
        ),
    ),
    "veo_3_1": VideoModelConfig(
        key="veo_3_1",
        label="Veo 3.1",
        tier="Ultra-Profissional",
        application=_env_or_default(
            "HF_MODEL_VEO_3_1", "google/veo/3.1"
        ),
        allowed_resolutions=("720p", "1080p"),
        fallback_application=_env_or_default(
            "HF_MODEL_VEO_3_1_FALLBACK",
            "google/veo/v3.1/text-to-video",
        ),
        default_arguments={},
        fallback_note=(
            "Configure HF_MODEL_VEO_3_1 no .env se a sua conta usar outro application ID."
        ),
    ),
}


def get_model_config(model_key: VideoModelLiteral) -> VideoModelConfig:
    """Return a validated model configuration."""

    try:
        return VIDEO_MODEL_REGISTRY[model_key]
    except KeyError as exc:
        raise ValueError(f"Modelo de vídeo inválido: {model_key}") from exc
