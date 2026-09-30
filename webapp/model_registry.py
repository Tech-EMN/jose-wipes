"""Registry of user-facing video models for the web studio."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

from scripts.higgsfield_model_profiles import (
    KLING_3_0_PRO_APPLICATION,
    KLING_3_0_STD_APPLICATION,
    WAN_3_0_PRIME_APPLICATION,
)
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


ALL_RESOLUTIONS: tuple[ResolutionLiteral, ...] = ("720p", "1080p")
FALLBACK_APPLICATION = KLING_3_0_PRO_APPLICATION

_STANDARD_TIER = VideoModelConfig(
    key="seedance_1_5_pro",
    label="Kling 3.0 Std — Padrão",
    tier="Padrão",
    application=_env_or_default("HF_MODEL_PADRAO", KLING_3_0_STD_APPLICATION),
    allowed_resolutions=ALL_RESOLUTIONS,
    fallback_application=FALLBACK_APPLICATION,
    fallback_note=(
        "Kling 3.0 Std via Higgsfield. Se o modelo estiver indisponível, cai para o Kling 3.0 Pro. "
        "Defina HF_MODEL_PADRAO para trocar de modelo sem deploy."
    ),
)

_REALISTIC_TIER = VideoModelConfig(
    key="kling_3_0",
    label="Kling 3.0 — Realista",
    tier="Realista",
    application=_env_or_default("HF_MODEL_KLING_3_0", KLING_3_0_PRO_APPLICATION),
    allowed_resolutions=ALL_RESOLUTIONS,
    fallback_note=(
        "Kling 3.0 Pro via Higgsfield, sem áudio nativo (a narração vem do ElevenLabs). "
        "Defina HF_MODEL_KLING_3_0 para trocar de modelo sem deploy."
    ),
)

_PROFESSIONAL_TIER = VideoModelConfig(
    key="veo_3_1",
    label="Wan 3.0 Prime — Profissional",
    tier="Profissional",
    application=_env_or_default("HF_MODEL_PROFISSIONAL", WAN_3_0_PRIME_APPLICATION),
    allowed_resolutions=ALL_RESOLUTIONS,
    fallback_application=FALLBACK_APPLICATION,
    fallback_note=(
        "Wan 3.0 Prime via Higgsfield, 1080p nativo. Se o modelo estiver indisponível, cai para o Kling 3.0 Pro. "
        "Defina HF_MODEL_PROFISSIONAL para trocar de modelo sem deploy."
    ),
)

VIDEO_MODEL_REGISTRY: dict[VideoModelLiteral, VideoModelConfig] = {
    "seedance_1_5_pro": _STANDARD_TIER,
    "kling_3_0": _REALISTIC_TIER,
    "veo_3_1": _PROFESSIONAL_TIER,
    "sora_2": replace(_STANDARD_TIER, key="sora_2"),
    "sora_2_pro": replace(_PROFESSIONAL_TIER, key="sora_2_pro"),
}


def get_model_config(model_key: VideoModelLiteral) -> VideoModelConfig:
    """Return a validated model configuration."""

    try:
        return VIDEO_MODEL_REGISTRY[model_key]
    except KeyError as exc:
        raise ValueError(f"Modelo de vídeo inválido: {model_key}") from exc
