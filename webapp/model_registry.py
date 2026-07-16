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


# Único modelo confirmado como disponível nesta conta Higgsfield:
#   kling-video/v2.1/master/text-to-video  (Kling 2.1 Master)
# Atualizado após diagnóstico de 2026-07-16 (scripts/descobrir_modelos_higgsfield.py).
# Use as env vars HF_MODEL_* para sobrescrever quando novos modelos forem contratados.

_KW_2_1 = "kling-video/v2.1/master/text-to-video"

VIDEO_MODEL_REGISTRY: dict[VideoModelLiteral, VideoModelConfig] = {
    "seedance_1_5_pro": VideoModelConfig(
        key="seedance_1_5_pro",
        label="Kling 2.1 — Padrão",
        tier="Padrão",
        application=_env_or_default(
            "HF_MODEL_SEEDANCE_1_5_PRO", _KW_2_1
        ),
        allowed_resolutions=("720p", "1080p"),
        fallback_application="",
        default_arguments={},
        fallback_note=(
            "Sua conta atual só possui Kling 2.1. "
            "Defina HF_MODEL_SEEDANCE_1_5_PRO no .env quando contratar Seedance."
        ),
    ),
    "kling_3_0": VideoModelConfig(
        key="kling_3_0",
        label="Kling 2.1 — Realista",
        tier="Realista",
        application=_env_or_default(
            "HF_MODEL_KLING_3_0", _KW_2_1
        ),
        allowed_resolutions=("720p", "1080p"),
        fallback_application="",
        default_arguments={},
        fallback_note=(
            "Sua conta atual só possui Kling 2.1. "
            "Defina HF_MODEL_KLING_3_0 no .env quando contratar Kling 3.0."
        ),
    ),
    "veo_3_1": VideoModelConfig(
        key="veo_3_1",
        label="Kling 2.1 — Profissional",
        tier="Profissional",
        application=_env_or_default(
            "HF_MODEL_VEO_3_1", _KW_2_1
        ),
        allowed_resolutions=("720p", "1080p"),
        fallback_application="",
        default_arguments={},
        fallback_note=(
            "Sua conta atual só possui Kling 2.1. "
            "Defina HF_MODEL_VEO_3_1 no .env quando contratar Veo."
        ),
    ),
}


def get_model_config(model_key: VideoModelLiteral) -> VideoModelConfig:
    """Return a validated model configuration."""

    try:
        return VIDEO_MODEL_REGISTRY[model_key]
    except KeyError as exc:
        raise ValueError(f"Modelo de vídeo inválido: {model_key}") from exc
