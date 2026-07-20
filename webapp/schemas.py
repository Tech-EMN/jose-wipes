"""Typed schemas used by the web video studio."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


ResolutionLiteral = Literal["720p", "1080p"]
OrientationLiteral = Literal["vertical", "horizontal"]
DurationLiteral = Literal[10, 30, 60]
VideoModelLiteral = Literal["seedance_1_5_pro", "kling_3_0", "veo_3_1", "sora_2", "sora_2_pro"]

VALID_VOICE_PERSONAS = {"narrador", "joao", "lider", "amigo"}


class CreateJobRequest(BaseModel):
    """Validated form payload for a new web job."""

    resolution: ResolutionLiteral
    orientation: OrientationLiteral
    duration_seconds: DurationLiteral
    prompt: str = Field(min_length=1, max_length=4000)
    video_model: VideoModelLiteral

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("O prompt não pode estar vazio.")
        return value


class ProductOverlayConfig(BaseModel):
    """Overlay instructions for the real José Wipes package."""

    ativo: bool = False
    posicao: Literal["centro", "centro_inferior", "direita", "esquerda"] = "centro"
    tamanho_pct: int = Field(default=55, ge=15, le=75)
    inicio_seg: float | None = Field(default=None, ge=0)


class PlannerShot(BaseModel):
    """Single 5-second shot planned by OpenAI."""

    shot_number: int = Field(ge=1)
    visual_prompt_en: str = Field(min_length=20)
    duration_seconds: int = Field(default=5, gt=0)
    narration_text_pt: str = ""
    voice_persona: str = "narrador"
    overlay_text: str | None = None
    product_overlay: ProductOverlayConfig = Field(default_factory=ProductOverlayConfig)
    notes: str | None = None

    @field_validator("voice_persona")
    @classmethod
    def normalize_voice_persona(cls, value: str) -> str:
        value = (value or "narrador").strip().lower()
        if value not in VALID_VOICE_PERSONAS:
            return "narrador"
        return value

    @field_validator("narration_text_pt")
    @classmethod
    def trim_narration(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("overlay_text")
    @classmethod
    def trim_overlay(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class PlannerOutput(BaseModel):
    """Normalized planner result for the render pipeline."""

    title: str = Field(min_length=1, max_length=120)
    enhanced_brief_pt: str = Field(min_length=1)
    global_style: str = Field(min_length=1)
    final_cta_pt: str = Field(min_length=1)
    notes: str | None = None
    shots: list[PlannerShot] = Field(min_length=1)

    @field_validator("title", "enhanced_brief_pt", "global_style", "final_cta_pt")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("notes")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class JobStatusResponse(BaseModel):
    """Public status payload returned by the web API."""

    job_id: str
    status: str
    step: str
    progress_message: str
    warnings: list[str] = Field(default_factory=list)
    title: str | None = None
    enhanced_brief: str | None = None
    preview_url: str | None = None
    download_url: str | None = None
    error_message: str | None = None
    failed_stage: str | None = None
    failed_service: str | None = None
    failure_code: str | None = None
    retryable: bool | None = None
    user_message: str | None = None
    auth_confirmed: bool | None = None
    submit_confirmed: bool | None = None
    render_confirmed: bool | None = None
    failure_reason: str | None = None


class ExternalServiceHealth(BaseModel):
    """Health information for one external integration."""

    ok: bool
    status: Literal["ok", "error"]
    message: str
    auth_confirmed: bool | None = None
    submit_confirmed: bool | None = None
    render_confirmed: bool | None = None
    reason: str | None = None


class ExternalHealthResponse(BaseModel):
    """Structured health response for the web UI."""

    ready_for_submit: bool
    checked_at: str
    startup_mode: str | None = None
    external_connectivity_checked: bool | None = None
    services: dict[str, ExternalServiceHealth]
