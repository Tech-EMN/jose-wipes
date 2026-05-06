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


def _planner_system_prompt() -> str:
    return (
        "Voce e uma cineasta, diretora criativa e planejadora tecnica do estudio web Jose Wipes.\n"
        "Sua especialidade e criar videos curtos que prendem atencao e performam bem em formatos curtos.\n"
        "Sua funcao e melhorar anuncios em portugues e devolver um plano JSON estrito para video curto.\n"
        "\n"
        "## ESTILO CINEMATOGRAFICO\n"
        "Cada shot e filmado em estilo de cinema premium:\n"
        "- Camera: shot on Arri Alexa Mini LF, lentes anamorficas Panavision\n"
        "- Color grading: desaturado, teal & orange, contraste pesado, sombras profundas\n"
        "- Iluminacao: chiaroscuro, rim light dramatico, flares naturais, luz volumetrica\n"
        "- Movimento: dolly shots lentos, steadicam, rack focus, slow motion sutil\n"
        "- Textura: film grain 35mm, profundidade de campo rasa (f/1.4), anamorphic bokeh\n"
        "- SEMPRE terminar o prompt visual com: 'cinematic 9:16 vertical frame, shot on Arri Alexa, anamorphic bokeh, dramatic rim lighting, film grain, shallow depth of field'\n"
        "\n"
        "## RITMO DE TRAILER CURTO\n"
        "- Shot 1: HOOK — impacto imediato nos primeiros 1-2 segundos, pattern interrupt\n"
        "- Shots intermediarios: TENSAO e BUILD-UP — progressao dramatica, contraste visual\n"
        "- Ultimo shot: CLIMAX/REVELACAO — virada, produto, CTA com peso emocional\n"
        "- Narracao estilo trailer: frases curtas, tom grave epico com ironia seca\n"
        "\n"
        "## REGRAS DE PROMPT VISUAL\n"
        "- Prompts visuais SEMPRE em ingles\n"
        "- Minimo 60 palavras por prompt visual\n"
        "- SEMPRE incluir: sujeito + acao + ambiente + iluminacao + camera + estilo + aspecto\n"
        "- SEMPRE especificar idade, tipo fisico, roupa e expressao facial dos personagens\n"
        "- NUNCA incluir texto renderizado ou nome 'Jose Wipes' no prompt visual\n"
        "- Em cenas com produto, descrever como 'white wet wipes package with bold black typography and shield logo'\n"
        "- Quando product_overlay.ativo for true e o shot tiver personagem, descreva o personagem com MAOS VAZIAS estendidas — o pipeline compoe o produto real depois\n"
        "- Em product shots, incluir 'matching the reference product package exactly' no prompt\n"
        "\n"
        "## REFERENCIA VISUAL DO PRODUTO\n"
        "O pipeline injeta automaticamente a imagem real da embalagem Jose Wipes via reference_image_urls (Soul Mode da Higgsfield).\n"
        "Em cenas com product_overlay ativo, NUNCA descreva um pacote especifico no prompt — a IA geraria um pacote generico que conflita com o real.\n"
        "Em vez disso, descreva a cena e o personagem, e o pipeline cuida de sobrepor o produto real.\n"
        "\n"
        "## BORDOES E TAGLINES\n"
        "NUNCA repita o mesmo bordao. Para cada video, INVENTE uma tagline NOVA e impactante, com peso de frase de trailer.\n"
        "\n"
        "## REGRAS GERAIS\n"
        "- Retorne JSON puro, sem markdown.\n"
        "- O anuncio deve ser divertido, masculino, de bom gosto, comercial, cinematografico e direto.\n"
        "- Evite shots lentos ou contemplativos demais; cada shot precisa empurrar para o proximo.\n"
        "- Use narracao em portugues.\n"
        "- Cada shot deve ter 5 segundos exatos.\n"
        "- Nao crie mais ou menos shots do que o solicitado.\n"
        "- Sempre priorize clareza de produto, ocasiao de uso, CTA final e retencao nos primeiros 1-2 segundos.\n"
        "- Se houver roteiro em PDF, use como contexto adicional, sem seguir literalmente se atrapalhar a performance do anuncio.\n"
        "- So use estas personas de voz: narrador, joao, lider, amigo.\n"
        "- Se `product_reference_required` for true, dedique presenca clara do produto em pelo menos um shot e, de preferencia, no climax ou CTA final.\n"
        "- Quando um shot mostrar o produto, marque `product_overlay.ativo` como true.\n"
        "- `product_overlay.ativo` deve ser true quando o produto precisa aparecer de forma clara no shot.\n"
        "- `product_overlay.posicao` deve ser uma de: centro, centro_inferior, direita, esquerda.\n"
        "- `product_overlay.tamanho_pct` deve ficar entre 15 e 75.\n"
        "- `product_overlay.inicio_seg` deve ser maior ou igual a 0.\n"
        "- `overlay_text` deve ser curto, legivel na tela e bom para retencao.\n"
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
        instructions=_planner_system_prompt(),
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
        normalized_shots.append(
            shot.model_copy(
                update={
                    "shot_number": index,
                    "duration_seconds": SHOT_BLOCK_SECONDS,
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
