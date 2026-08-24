"""Render planned José Wipes videos inside isolated job folders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from scripts.compositor import (
    adicionar_logo_overlay,
    adicionar_texto_overlay,
    compor_video_final,
    gerar_card_logo,
    overlay_produto,
)
from scripts.config import obter_path_imagem_produto, obter_url_imagem_produto
from scripts.product_reference import prompt_pede_referencia_produto
from scripts.gerador_midia import (
    combinar_video_audio,
    gerar_audio_elevenlabs,
    gerar_video_higgsfield,
)
from scripts.integration_errors import IntegrationFailure
from scripts.higgsfield_utils import upload_higgsfield_file
from scripts.uploader import upload_para_drive
from webapp.model_registry import VideoModelConfig
from webapp.schemas import CreateJobRequest, PlannerOutput


ProgressCallback = Callable[[str, str], None]


def _required_step_failure(
    *,
    service: str,
    stage: str,
    code: str,
    message: str,
    render_confirmed: bool | None = None,
) -> IntegrationFailure:
    return IntegrationFailure(
        service=service,
        stage=stage,
        code=code,
        user_message=message,
        technical_message=message,
        retryable=True,
        render_confirmed=render_confirmed,
        reason=code,
    )


def _gerar_video_com_fallback(
    model_config: VideoModelConfig,
    prompt: str,
    *,
    aspecto: str,
    resolucao: str,
    duracao: int,
    output_path: str,
    reference_image_url: str | None,
    reference_image_path: Path | None,
    extra_arguments: dict,
) -> "Path | None":
    """Generate video with automatic fallback using VideoGenerator interface."""
    import logging
    _log = logging.getLogger(__name__)

    from webapp.video_generator import (
        VideoGenerationRequest,
        create_video_generator,
    )

    applications = [model_config.application]
    if model_config.fallback_application:
        applications.append(model_config.fallback_application)

    last_exc: IntegrationFailure | None = None
    for app in applications:
        try:
            generator = create_video_generator(
                app,
                extra_arguments=extra_arguments,
            )
            request = VideoGenerationRequest(
                prompt=prompt,
                aspect_ratio=aspecto,
                resolution=resolucao,
                duration_seconds=duracao,
                output_path=Path(output_path),
                reference_image_url=reference_image_url,
                reference_image_path=reference_image_path,
            )
            result = generator.generate(request)
            return result.output_path
        except IntegrationFailure as exc:
            last_exc = exc
            if app != applications[-1]:
                _log.warning(
                    "Modelo '%s' falhou; tentando fallback '%s'.",
                    app,
                    applications[applications.index(app) + 1],
                )
                continue
            raise

    if last_exc is not None:
        raise last_exc
    return None

VIDEO_DIMENSIONS = {
    ("vertical", "720p"): (720, 1280),
    ("vertical", "1080p"): (1080, 1920),
    ("horizontal", "720p"): (1280, 720),
    ("horizontal", "1080p"): (1920, 1080),
}

ASPECT_RATIO_BY_ORIENTATION = {
    "vertical": "9:16",
    "horizontal": "16:9",
}


def _upload_reference_image(image_path: str | Path | None) -> str | None:
    """Upload a reference image to Higgsfield and return its URL.

    Retries with exponential backoff on transient failures:
    - 3 attempts total
    - Backoff: 2s → 4s → 8s
    - Returns URL on success, None after all retries exhausted
    """
    import logging
    import time

    _log = logging.getLogger(__name__)

    if not image_path:
        return None
    path = Path(image_path)
    if not path.exists():
        return None

    max_retries = 3
    base_delay = 2.0

    for attempt in range(1, max_retries + 1):
        try:
            url = upload_higgsfield_file(path)
            if attempt > 1:
                _log.info(
                    "Reference image upload succeeded on attempt %d/%d",
                    attempt, max_retries,
                )
            return url
        except Exception as exc:
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                _log.warning(
                    "Reference image upload failed (attempt %d/%d): %s. "
                    "Retrying in %.1fs...",
                    attempt, max_retries, exc, delay,
                )
                time.sleep(delay)
            else:
                _log.error(
                    "Reference image upload failed after %d attempts: %s",
                    max_retries, exc,
                )
                return None

    return None


def render_planned_video(
    *,
    job_dir: Path,
    request: CreateJobRequest,
    plan: PlannerOutput,
    model_config: VideoModelConfig,
    progress_cb: ProgressCallback | None = None,
    ref_embalagem_path: str | None = None,
    ref_logo_path: str | None = None,
    ref_cores_path: str | None = None,
    apply_logo_overlay: bool = True,
) -> dict[str, object]:
    """Generate all scenes for a job and compose the final video."""

    cenas_dir = job_dir / "cenas"
    final_dir = job_dir / "final"
    cenas_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    aspect_ratio = ASPECT_RATIO_BY_ORIENTATION[request.orientation]
    largura, altura = VIDEO_DIMENSIONS[(request.orientation, request.resolution)]

    if request.resolution not in model_config.allowed_resolutions:
        raise ValueError(
            f"Resolução {request.resolution} não é suportada pelo modelo {model_config.label}."
        )

    # Determine which reference image to use for product shots
    # Priority: user-uploaded embalagem > default product image
    reference_image_url = None
    reference_image_path = None
    shot_reference_flags = [
        not shot.product_overlay.ativo
        and prompt_pede_referencia_produto(
            shot.visual_prompt_en,
            shot.narration_text_pt,
            shot.overlay_text,
            shot.notes,
        )
        for shot in plan.shots
    ]

    if any(shot_reference_flags):
        if ref_embalagem_path:
            reference_image_path = Path(ref_embalagem_path)
            # Upload user-provided packaging image
            if progress_cb:
                progress_cb("uploading_ref", "Enviando imagem da embalagem como referência...")
            uploaded_url = _upload_reference_image(ref_embalagem_path)
            if uploaded_url:
                reference_image_url = uploaded_url
            else:
                warnings.append("Não foi possível enviar a embalagem do usuário; usando padrão.")
                try:
                    reference_image_url = obter_url_imagem_produto()
                except Exception as exc:
                    warnings.append(f"Referência visual do produto indisponível: {exc}")
        else:
            default_product = obter_path_imagem_produto()
            if default_product and Path(default_product).exists():
                reference_image_path = Path(default_product)
            try:
                reference_image_url = obter_url_imagem_produto()
            except Exception as exc:
                warnings.append(f"Referência visual do produto indisponível: {exc}")

    # Only apply logo overlay when the user explicitly uploaded a logo
    logo_path_to_use = None
    if apply_logo_overlay and ref_logo_path and Path(ref_logo_path).exists():
        logo_path_to_use = Path(ref_logo_path)

    # Determine product overlay image
    # Priority: user-uploaded embalagem > default product
    produto_overlay_path = None
    if ref_embalagem_path and Path(ref_embalagem_path).exists():
        produto_overlay_path = Path(ref_embalagem_path)

    rendered_scenes: list[str] = []
    total_shots = len(plan.shots)

    for shot_index, shot in enumerate(plan.shots):
        should_use_reference = shot_reference_flags[shot_index]
        if progress_cb:
            progress_cb(
                "generating",
                f"Gerando cena {shot.shot_number}/{total_shots}: {plan.title}",
            )

        base_path = cenas_dir / f"shot_{shot.shot_number:02d}"
        video_path = _gerar_video_com_fallback(
            model_config,
            shot.visual_prompt_en,
            aspecto=aspect_ratio,
            resolucao=request.resolution,
            duracao=shot.duration_seconds,
            output_path=f"{base_path}.mp4",
            reference_image_url=reference_image_url if should_use_reference else None,
            reference_image_path=reference_image_path if should_use_reference else None,
            extra_arguments=model_config.default_arguments,
        )
        if not video_path:
            raise RuntimeError(
                f"Falha na geração da cena {shot.shot_number} usando {model_config.label}."
            )

        current_video_path = Path(video_path)

        if shot.narration_text_pt:
            audio_path = gerar_audio_elevenlabs(
                shot.voice_persona,
                shot.narration_text_pt,
                f"{base_path}_audio.mp3",
            )
            if audio_path:
                combined_path = combinar_video_audio(
                    current_video_path,
                    audio_path,
                    f"{base_path}_combined.mp4",
                )
                if combined_path:
                    current_video_path = Path(combined_path)
                else:
                    raise _required_step_failure(
                        service="ffmpeg",
                        stage="composing_audio",
                        code="audio_composition_failed",
                        message=f"Falha ao combinar a narração da cena {shot.shot_number}.",
                    )
            else:
                raise _required_step_failure(
                    service="elevenlabs",
                    stage="generating_audio",
                    code="narration_failed",
                    message=f"Falha ao gerar a narração da cena {shot.shot_number}.",
                )

        if shot.product_overlay.ativo:
            overlay_path = overlay_produto(
                current_video_path,
                f"{base_path}_produto.mp4",
                produto_path=produto_overlay_path,
                posicao=shot.product_overlay.posicao,
                tamanho_pct=shot.product_overlay.tamanho_pct,
                inicio_seg=shot.product_overlay.inicio_seg,
            )
            if overlay_path:
                current_video_path = Path(overlay_path)
            else:
                raise _required_step_failure(
                    service="ffmpeg",
                    stage="composing",
                    code="product_overlay_failed",
                    message=f"Falha ao aplicar a embalagem na cena {shot.shot_number}.",
                )

        if shot.overlay_text:
            text_path = adicionar_texto_overlay(
                current_video_path,
                shot.overlay_text,
                f"{base_path}_texto.mp4",
                "centro_inferior",
            )
            if text_path:
                current_video_path = Path(text_path)
            else:
                raise _required_step_failure(
                    service="ffmpeg",
                    stage="composing",
                    code="text_overlay_failed",
                    message=f"Falha ao aplicar o texto da cena {shot.shot_number}.",
                )

        rendered_scenes.append(str(current_video_path))

    # Card final com a logo/embalagem real da marca sobre fundo branco limpo
    card_image_path = None
    if ref_logo_path and Path(ref_logo_path).exists():
        card_image_path = Path(ref_logo_path)
    elif ref_embalagem_path and Path(ref_embalagem_path).exists():
        card_image_path = Path(ref_embalagem_path)
    else:
        default_product = obter_path_imagem_produto()
        if default_product and Path(default_product).exists():
            card_image_path = Path(default_product)

    if card_image_path:
        if progress_cb:
            progress_cb("composing", "Gerando card final com a logo da marca...")
        card_final_path = final_dir / "card_final_logo.mp4"
        card_video = gerar_card_logo(
            card_final_path,
            card_image_path,
            duracao=3,
            largura=largura,
            altura=altura,
        )
        if card_video:
            rendered_scenes.append(str(card_video))
        else:
            raise _required_step_failure(
                service="ffmpeg",
                stage="composing",
                code="brand_card_failed",
                message="Falha ao gerar o card final da marca.",
            )

    if progress_cb:
        progress_cb("composing", "Compondo vídeo final e aplicando marca da empresa...")

    final_video = compor_video_final(
        rendered_scenes,
        plan.title,
        logo_path_to_use if apply_logo_overlay else None,
        largura=largura,
        altura=altura,
        output_dir=final_dir,
        duracao_maxima=request.duration_seconds,
    )
    if not final_video:
        raise _required_step_failure(
            service="ffmpeg",
            stage="composing",
            code="final_video_invalid",
            message="Falha na composição ou validação do vídeo final.",
        )

    if progress_cb:
        progress_cb("uploading_drive", "Enviando vídeo final para o Google Drive...")
    drive_result = upload_para_drive(final_video)
    if not drive_result:
        raise _required_step_failure(
            service="google_drive",
            stage="uploading_drive",
            code="drive_upload_failed",
            message="Falha ao entregar o vídeo final no Google Drive.",
            render_confirmed=True,
        )

    manifest_path = job_dir / "manifesto_render.json"
    manifest_path.write_text(
        json.dumps(
            {
                "titulo": plan.title,
                "modelo_video": model_config.label,
                "modelo_tier": model_config.tier,
                "aspect_ratio": aspect_ratio,
                "resolucao": request.resolution,
                "cenas": rendered_scenes,
                "saida_final": str(final_video),
                "google_drive": drive_result,
                "ref_embalagem_usada": ref_embalagem_path or "padrão",
                "ref_logo_usada": str(logo_path_to_use) if logo_path_to_use else "nenhuma",
                "logo_overlay_aplicado": apply_logo_overlay,
                "warnings": warnings,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return {
        "final_video_path": str(final_video),
        "drive_file_id": drive_result.get("id") if drive_result else None,
        "drive_url": drive_result.get("link") if drive_result else None,
        "warnings": warnings,
    }
