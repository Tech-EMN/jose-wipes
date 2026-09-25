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


KLING_3_0_PRO_APPLICATION = "kling-video/v3.0/pro/text-to-video"
KLING_3_0_DEFAULT_ARGUMENTS: dict[str, object] = {"sound": "off"}

VIDEO_MODEL_REGISTRY: dict[VideoModelLiteral, VideoModelConfig] = {
    "seedance_1_5_pro": VideoModelConfig(
        key="seedance_1_5_pro",
        label="Sora-2 — Padrão",
        tier="Padrão",
        application="openai:sora-2",
        allowed_resolutions=("720p", "1080p"),
        fallback_application="",
        default_arguments={},
        fallback_note=(
            "Sora-2 gera vídeos de 4/8/12s via OpenAI. "
            "Durações do planner (5s/shot) são arredondadas para 4s."
        ),
    ),
    "kling_3_0": VideoModelConfig(
        key="kling_3_0",
        label="Kling 3.0 — Realista",
        tier="Realista",
        application=_env_or_default(
            "HF_MODEL_KLING_3_0", KLING_3_0_PRO_APPLICATION
        ),
        allowed_resolutions=("720p", "1080p"),
        fallback_application="",
        default_arguments=KLING_3_0_DEFAULT_ARGUMENTS,
        fallback_note=(
            "Kling 3.0 Pro via Higgsfield, sem áudio nativo (a narração vem do ElevenLabs). "
            "Defina HF_MODEL_KLING_3_0 para usar outra variante, ex.: kling-video/v3.0/std/text-to-video."
        ),
    ),
    "veo_3_1": VideoModelConfig(
        key="veo_3_1",
        label="Sora-2-Pro — Profissional",
        tier="Profissional",
        application="openai:sora-2-pro",
        allowed_resolutions=("720p", "1080p"),
        fallback_application="",
        default_arguments={},
        fallback_note=(
            "Sora-2-Pro: qualidade máxima OpenAI. "
            "Durações do planner (5s/shot) são arredondadas para 4s."
        ),
    ),
    "sora_2": VideoModelConfig(
        key="sora_2",
        label="Sora-2 — Padrão",
        tier="Padrão",
        application="openai:sora-2",
        allowed_resolutions=("720p", "1080p"),
        fallback_application="",
        default_arguments={},
        fallback_note="Sora-2 via OPENAI_API_KEY. 4/8/12s suportados.",
    ),
    "sora_2_pro": VideoModelConfig(
        key="sora_2_pro",
        label="Sora-2-Pro — Profissional",
        tier="Profissional",
        application="openai:sora-2-pro",
        allowed_resolutions=("720p", "1080p"),
        fallback_application="",
        default_arguments={},
        fallback_note="Sora-2-Pro via OPENAI_API_KEY. Qualidade máxima.",
    ),
}


def get_model_config(model_key: VideoModelLiteral) -> VideoModelConfig:
    """Return a validated model configuration."""

    try:
        return VIDEO_MODEL_REGISTRY[model_key]
    except KeyError as exc:
        raise ValueError(f"Modelo de vídeo inválido: {model_key}") from exc
