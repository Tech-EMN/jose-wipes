"""OpenAI planning layer for the Jose Wipes web studio."""

from __future__ import annotations

import json
import math
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError

from scripts.config import (
    OPENAI_API_KEY,
    OPENAI_PLANNER_MODEL,
    brandbook_para_contexto,
    carregar_vozes,
)
from scripts.integration_errors import IntegrationFailure
from scripts.openai_utils import create_text_response
from scripts.product_reference import (
    detectar_gatilhos_referencia_produto,
    prompt_pede_referencia_produto,
)
from webapp.model_registry import VideoModelConfig
from webapp.schemas import CreateJobRequest, PlannerOutput, PlannerShot, ProductOverlayConfig


PLANNER_MODEL = OPENAI_PLANNER_MODEL
SHOT_BLOCK_SECONDS = 5
ALLOWED_PRODUCT_POSITIONS = {"centro", "centro_inferior", "direita", "esquerda"}

# Palavras por segundo confortáveis para o ElevenLabs multilingual em pt-BR
# considerando pausas dramáticas — ~2.0 wps mantém a fala dentro do shot.
NARRATION_WORDS_PER_SECOND = 2.0
# Reservamos 0.6s no fim do shot pra evitar corte de áudio mesmo com pad.
NARRATION_TAIL_RESERVE_SECONDS = 0.6
# Quando há personagem com gesto/embalagem na mão, atrasamos o overlay.
PRODUCT_OVERLAY_HAND_DELAY_SECONDS = 2.0
PRODUCT_OVERLAY_HAND_KEYWORDS = (
    "raises",
    "raising",
    "lifts",
    "lifting",
    "holds up",
    "holding up",
    "extends",
    "extending",
    "reveals",
    "revealing",
    "pulls out",
    "pulling out",
    "presents",
    "presenting",
    "hands extended",
    "hands raised",
    "hand reaches",
    "reaching",
    "showing the",
    "shows the",
)


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _voice_catalog_text() -> str:
    vozes = carregar_vozes()
    linhas = []
    for persona, config in vozes.items():
        linhas.append(
            f"- {persona}: {config.get('descricao', '').strip() or 'sem descricao'}"
        )
    return "\n".join(linhas) or "- narrador: voz padrao institucional"


def _expected_shot_count(duration_seconds: int) -> int:
    return duration_seconds // SHOT_BLOCK_SECONDS


def _planner_system_prompt(*, orientation: str = "vertical") -> str:
    """Load the planner system prompt from config/ and format with orientation params.

    The prompt lives in config/planner_system_prompt.txt so it can be:
    - versioned independently of code changes
    - A/B tested without redeploy
    - edited by non-developers

    Returns the formatted prompt string.
    """
    from scripts.config import CONFIG_DIR

    prompt_path = CONFIG_DIR / "planner_system_prompt.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Planner system prompt not found at {prompt_path}. "
            "Create config/planner_system_prompt.txt or restore from git."
        )

    template = prompt_path.read_text(encoding="utf-8")

    is_vertical = orientation == "vertical"
    aspect_ratio = "9:16" if is_vertical else "16:9"
    aspect_label = "vertical" if is_vertical else "horizontal"
    composition_hint = (
        "composicao VERTICAL com sujeito centralizado, headroom curto, planos fechados/medios"
        if is_vertical
        else "composicao HORIZONTAL cinematografica em widescreen, com headroom equilibrado"
    )
    aspect_tail = (
        f"cinematic {aspect_ratio} {aspect_label} frame, "
        "shot on Arri Alexa, anamorphic bokeh, dramatic rim lighting, "
        "film grain, shallow depth of field"
    )
    max_words = _max_narration_words(SHOT_BLOCK_SECONDS)

    return template.format(
        aspect_label=aspect_label,
        aspect_ratio=aspect_ratio,
        composition_hint=composition_hint,
        aspect_tail=aspect_tail,
        shot_duration=SHOT_BLOCK_SECONDS,
        max_words=max_words,
    )


def _prompt_content_hash() -> str:
    """Return SHA256 hash of the planner system prompt for version tracking."""
    import hashlib
    from scripts.config import CONFIG_DIR

    prompt_path = CONFIG_DIR / "planner_system_prompt.txt"
    if not prompt_path.exists():
        return "unknown"

    return hashlib.sha256(prompt_path.read_bytes()).hexdigest()[:12]


def _max_narration_words(shot_duration_seconds: int) -> int:
    """Maximo de palavras que cabem confortavelmente no shot considerando reserva no fim."""
    speakable = max(1.0, shot_duration_seconds - NARRATION_TAIL_RESERVE_SECONDS)
    return max(3, int(speakable * NARRATION_WORDS_PER_SECOND))


def _trim_narration_to_fit(text: str, shot_duration_seconds: int) -> str:
    """Garante que a narracao caiba no shot. Corta em fronteira de palavra/pontuacao."""
    if not text:
        return text
    words = text.split()
    limit = _max_narration_words(shot_duration_seconds)
    if len(words) <= limit:
        return text
    trimmed = words[:limit]
    # Tenta terminar em pontuacao para nao soar truncado
    for idx in range(len(trimmed) - 1, max(len(trimmed) - 4, -1), -1):
        if trimmed[idx].endswith((".", "!", "?", ",", "...")):
            trimmed = trimmed[: idx + 1]
            break
    else:
        trimmed[-1] = trimmed[-1].rstrip(",;:") + "."
    return " ".join(trimmed)


def _shot_descreve_gesto(shot: PlannerShot) -> bool:
    """Detecta se o shot envolve gesto de revelar/erguer (mao subindo, etc)."""
    haystack = " ".join(
        part.lower()
        for part in (shot.visual_prompt_en or "", shot.notes or "")
        if part
    )
    if not haystack:
        return False
    return any(keyword in haystack for keyword in PRODUCT_OVERLAY_HAND_KEYWORDS)


def _ajustar_overlay_para_gesto(shot: PlannerShot) -> PlannerShot:
    """Atrasa o overlay do produto quando o shot tem gesto de revelar."""
    if not shot.product_overlay.ativo:
        return shot
    if not _shot_descreve_gesto(shot):
        return shot
    inicio_atual = shot.product_overlay.inicio_seg or 0.0
    if inicio_atual >= PRODUCT_OVERLAY_HAND_DELAY_SECONDS:
        return shot
    # Nao ultrapassar a duracao do shot menos uma cauda visivel
    teto = max(0.5, shot.duration_seconds - 1.0)
    novo_inicio = min(PRODUCT_OVERLAY_HAND_DELAY_SECONDS, teto)
    return shot.model_copy(
        update={
            "product_overlay": ProductOverlayConfig(
                ativo=True,
                posicao=shot.product_overlay.posicao,
                tamanho_pct=shot.product_overlay.tamanho_pct,
                inicio_seg=novo_inicio,
            )
        }
    )


def _shot_pede_referencia_produto(shot: PlannerShot) -> bool:
    if shot.product_overlay.ativo:
        return True

    return prompt_pede_referencia_produto(
        shot.visual_prompt_en,
        shot.narration_text_pt,
        shot.overlay_text,
        shot.notes,
    )


def _write_planner_artifact(
    artifacts_dir: Path | None,
    filename: str,
    payload: object,
) -> None:
    if not artifacts_dir:
        return

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / filename).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "sim", "ativo"}:
            return True
        if normalized in {"false", "0", "no", "nao", "inativo"}:
            return False
    return default


def _normalize_overlay_position(value: object) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ALLOWED_PRODUCT_POSITIONS:
            return normalized
    return "centro"


def _normalize_overlay_size(value: object) -> int:
    if isinstance(value, bool):
        return 55
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 55

    if not math.isfinite(numeric):
        return 55
    return max(15, min(75, int(round(numeric))))


def _normalize_overlay_start(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0

    if not math.isfinite(numeric) or numeric < 0:
        return 0.0
    return numeric


def _sanitize_product_overlay(raw_overlay: object) -> dict[str, object]:
    overlay = raw_overlay if isinstance(raw_overlay, dict) else {}
    return {
        "ativo": _coerce_bool(overlay.get("ativo"), default=False),
        "posicao": _normalize_overlay_position(overlay.get("posicao")),
        "tamanho_pct": _normalize_overlay_size(overlay.get("tamanho_pct")),
        "inicio_seg": _normalize_overlay_start(overlay.get("inicio_seg")),
    }


def _sanitize_shot_payload(raw_shot: object) -> object:
    if not isinstance(raw_shot, dict):
        return raw_shot

    sanitized_shot = dict(raw_shot)
    sanitized_shot["product_overlay"] = _sanitize_product_overlay(
        raw_shot.get("product_overlay")
    )
    return sanitized_shot


def _sanitize_planner_payload(raw_payload: object) -> object:
    if not isinstance(raw_payload, dict):
        return raw_payload

    sanitized_payload = dict(raw_payload)
    raw_shots = raw_payload.get("shots")
    if isinstance(raw_shots, list):
        sanitized_payload["shots"] = [_sanitize_shot_payload(shot) for shot in raw_shots]
    return sanitized_payload


def _invalid_planner_payload_failure(message: str) -> IntegrationFailure:
    return IntegrationFailure(
        service="openai",
        stage="planning",
        code="invalid_planner_payload",
        user_message=(
            "A OpenAI retornou um plano invalido para o Web Studio. Revise o prompt ou tente novamente."
        ),
        technical_message=message,
        retryable=True,
    )


def plan_web_video(
    request: CreateJobRequest,
    pdf_text: str,
    model_config: VideoModelConfig,
    *,
    artifacts_dir: Path | None = None,
) -> PlannerOutput:
    """Generate a structured shot plan for the web flow."""

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY nao configurada.")

    client = OpenAI(api_key=OPENAI_API_KEY)
    shot_count = _expected_shot_count(request.duration_seconds)
    product_reference_required = prompt_pede_referencia_produto(request.prompt, pdf_text)
    product_reference_matches = detectar_gatilhos_referencia_produto(request.prompt, pdf_text)

    user_payload = {
        "briefing_usuario": request.prompt,
        "roteiro_pdf_contexto": pdf_text or None,
        "product_reference_required": product_reference_required,
        "product_reference_triggers": product_reference_matches,
        "duracao_total_segundos": request.duration_seconds,
        "shots_necessarios": shot_count,
        "resolucao_desejada": request.resolution,
        "orientacao": request.orientation,
        "aspect_ratio": "9:16" if request.orientation == "vertical" else "16:9",
        "modelo_video_escolhido": model_config.label,
        "brandbook": json.loads(brandbook_para_contexto() or "{}"),
        "vozes_disponiveis": _voice_catalog_text(),
        "schema_esperado": {
            "title": "string",
            "enhanced_brief_pt": "string",
            "global_style": "string",
            "final_cta_pt": "string",
            "notes": "string",
            "shots": [
                {
                    "shot_number": 1,
                    "visual_prompt_en": "string",
                    "duration_seconds": 5,
                    "narration_text_pt": "string",
                    "voice_persona": "narrador|joao|lider|amigo",
                    "overlay_text": "string|null",
                    "product_overlay": {
                        "ativo": True,
                        "posicao": "centro|centro_inferior|direita|esquerda",
                        "tamanho_pct": 55,
                        "inicio_seg": 0,
                    },
                    "notes": "string",
                }
            ],
        },
    }

    # Scale token budget with shot count: reasoning overhead + ~1500 tokens/shot
    max_output_tokens = max(8000, 6000 + shot_count * 1500)
    raw_text = create_text_response(
        client=client,
        model=PLANNER_MODEL,
        instructions=_planner_system_prompt(orientation=request.orientation),
        user_input=json.dumps(user_payload, ensure_ascii=False),
        max_output_tokens=max_output_tokens,
    )

    try:
        raw_payload = json.loads(_strip_json_fences(raw_text))
    except json.JSONDecodeError as exc:
        _write_planner_artifact(
            artifacts_dir,
            "plano_web_raw.json",
            {"raw_text": raw_text},
        )
        raise _invalid_planner_payload_failure(f"Planner JSON invalido: {exc}") from exc

    _write_planner_artifact(artifacts_dir, "plano_web_raw.json", raw_payload)
    normalized_payload = _sanitize_planner_payload(raw_payload)
    _write_planner_artifact(
        artifacts_dir,
        "plano_web_normalizado.json",
        normalized_payload,
    )

    try:
        plan = PlannerOutput.model_validate(normalized_payload)
    except ValidationError as exc:
        raise _invalid_planner_payload_failure(str(exc)) from exc

    if len(plan.shots) != shot_count:
        raise _invalid_planner_payload_failure(
            f"O planejador retornou {len(plan.shots)} shots, mas {shot_count} eram esperados."
        )

    normalized_shots: list[PlannerShot] = []
    for index, shot in enumerate(plan.shots, start=1):
        trimmed_narration = _trim_narration_to_fit(
            shot.narration_text_pt, SHOT_BLOCK_SECONDS
        )
        normalized_shots.append(
            shot.model_copy(
                update={
                    "shot_number": index,
                    "duration_seconds": SHOT_BLOCK_SECONDS,
                    "narration_text_pt": trimmed_narration,
                }
            )
        )

    plan = plan.model_copy(update={"shots": normalized_shots})

    normalized_with_product: list[PlannerShot] = []
    for shot in plan.shots:
        if _shot_pede_referencia_produto(shot):
            normalized_with_product.append(
                shot.model_copy(
                    update={
                        "product_overlay": ProductOverlayConfig(
                            ativo=True,
                            posicao=shot.product_overlay.posicao,
                            tamanho_pct=shot.product_overlay.tamanho_pct,
                            inicio_seg=shot.product_overlay.inicio_seg,
                        )
                    }
                )
            )
        else:
            normalized_with_product.append(shot)

    plan = plan.model_copy(update={"shots": normalized_with_product})

    # Atrasa o overlay quando o shot tem gesto de revelar/erguer
    plan = plan.model_copy(
        update={"shots": [_ajustar_overlay_para_gesto(shot) for shot in plan.shots]}
    )

    last_shot = plan.shots[-1]
    if not last_shot.overlay_text:
        plan.shots[-1] = last_shot.model_copy(update={"overlay_text": plan.final_cta_pt})

    if product_reference_required and not plan.shots[-1].product_overlay.ativo:
        last_shot = plan.shots[-1]
        plan.shots[-1] = last_shot.model_copy(
            update={
                "product_overlay": ProductOverlayConfig(
                    ativo=True,
                    posicao="centro",
                    tamanho_pct=max(last_shot.product_overlay.tamanho_pct, 55),
                    inicio_seg=last_shot.product_overlay.inicio_seg,
                )
            }
        )

    return plan
