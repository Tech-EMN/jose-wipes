"""Render planned José Wipes videos inside isolated job folders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, get_args

from scripts.compositor import (
    BRAND_CARD_LOGO_WIDTH_PCT,
    LOGO_OVERLAY_WIDTH_PCT,
    adicionar_logo_overlay,
    adicionar_texto_overlay,
    compor_video_final,
    gerar_card_logo,
    imagem_tem_transparencia,
    obter_formato_imagem,
    overlay_produto,
)
from scripts.config import (
    JW_DRIVE_REQUIRED,
    obter_path_imagem_produto,
    obter_url_imagem_produto,
)
from scripts.product_reference import prompt_pede_referencia_produto
from scripts.gerador_midia import (
    combinar_video_audio,
    gerar_audio_elevenlabs,
    gerar_video_higgsfield,
    medir_duracao_segundos,
)
from scripts.higgsfield_model_profiles import ModelArgumentProfile, find_argument_profile
from scripts.integration_errors import IntegrationFailure
from scripts.higgsfield_utils import upload_higgsfield_file
from scripts.uploader import upload_para_drive
from webapp.model_registry import VideoModelConfig
from webapp.narration_plan import (
    BRAND_CARD_DURATION_SECONDS,
    DurationRange,
    NarrationClip,
    budget_warning,
    fit_narration_to_budget,
)
from webapp.schemas import CreateJobRequest, DurationLiteral, PlannerOutput


ProgressCallback = Callable[[str, str], None]
DEFAULT_SHOT_DURATION_RANGE = DurationRange(min_seconds=3, max_seconds=15)


def _faixa_de_duracao(model_config: VideoModelConfig) -> DurationRange:
    profiles = [
        profile
        for application in (model_config.application, model_config.fallback_application)
        if application
        and isinstance(profile := find_argument_profile(application), ModelArgumentProfile)
    ]
    if not profiles:
        return DEFAULT_SHOT_DURATION_RANGE
    return DurationRange(
        min_seconds=max(profile.min_duration_seconds for profile in profiles),
        max_seconds=min(profile.max_duration_seconds for profile in profiles),
    )


def _imagem_do_cartao(ref_logo_path: str | None, ref_embalagem_path: str | None) -> Path | None:
    for candidate in (ref_logo_path, ref_embalagem_path, obter_path_imagem_produto()):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def _largura_exibida(largura_video: int, tamanho_pct: float) -> int:
    return round(largura_video * float(tamanho_pct) / 100)


def _imagens_da_marca(
    plan: PlannerOutput,
    *,
    largura_video: int,
    produto_overlay_path: Path | None,
    logo_path: Path | None,
    card_image_path: Path | None,
) -> dict[Path, int]:
    exibicoes: dict[Path, int] = {}

    def registrar(image_path: Path | None, tamanho_pct: float) -> None:
        if image_path is None:
            return
        largura = _largura_exibida(largura_video, tamanho_pct)
        exibicoes[image_path] = max(exibicoes.get(image_path, 0), largura)

    overlays = [shot.product_overlay.tamanho_pct for shot in plan.shots if shot.product_overlay.ativo]
    if overlays:
        produto_padrao = obter_path_imagem_produto()
        registrar(produto_overlay_path or (Path(produto_padrao) if produto_padrao else None), max(overlays))
    registrar(logo_path, LOGO_OVERLAY_WIDTH_PCT)
    registrar(card_image_path, BRAND_CARD_LOGO_WIDTH_PCT)
    return exibicoes


def _avisos_qualidade_imagem(rotulo: str, image_path: Path, largura_exibida: int) -> list[str]:
    formato = obter_formato_imagem(image_path)
    if formato is None:
        return [f"Não foi possível analisar a imagem de {rotulo} ({image_path.name})."]

    largura, pix_fmt = formato
    avisos: list[str] = []
    if not imagem_tem_transparencia(pix_fmt):
        avisos.append(
            f"A imagem de {rotulo} não tem fundo transparente e vai aparecer com o fundo original no vídeo. "
            "Envie um PNG sem fundo."
        )
    if largura < largura_exibida:
        avisos.append(
            f"A imagem de {rotulo} tem {largura}px de largura, mas aparece com {largura_exibida}px no vídeo "
            f"e vai ficar borrada. Envie uma versão com pelo menos {largura_exibida}px."
        )
    return avisos


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


FALLBACK_ELIGIBLE_FAILURE_CODES = frozenset(
    {"model_blocked", "model_not_found", "provider_unavailable"}
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
            )
            result = generator.generate(request)
            return result.output_path
        except IntegrationFailure as exc:
            last_exc = exc
            if app != applications[-1] and exc.code in FALLBACK_ELIGIBLE_FAILURE_CODES:
                _log.warning(
                    "Modelo '%s' falhou (%s); tentando fallback '%s'.",
                    app,
                    exc.code,
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
    use_product_reference: bool = True,
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

    resolved_model = model_config.for_resolution(request.resolution)
    if resolved_model.application != model_config.application:
        warnings.append(
            f"Em {request.resolution}, o nível {model_config.tier} gera com {resolved_model.application}, "
            f"porque {model_config.application} não entrega essa resolução de forma nativa."
        )
    model_config = resolved_model

    # Determine which reference image to use for product shots
    # Priority: user-uploaded embalagem > default product image
    reference_image_url = None
    shot_reference_flags = [
        use_product_reference
        and not shot.product_overlay.ativo
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

    card_image_path = _imagem_do_cartao(ref_logo_path, ref_embalagem_path)
    card_duration = BRAND_CARD_DURATION_SECONDS if card_image_path else 0

    def sintetizar_narracao(shot_index: int, texto: str) -> NarrationClip:
        shot = plan.shots[shot_index]
        audio_path = gerar_audio_elevenlabs(
            shot.voice_persona,
            texto,
            f"{cenas_dir / f'shot_{shot.shot_number:02d}'}_audio.mp3",
        )
        if not audio_path:
            raise _required_step_failure(
                service="elevenlabs",
                stage="generating_audio",
                code="narration_failed",
                message=f"Falha ao gerar a narração da cena {shot.shot_number}.",
            )
        duracao_audio = medir_duracao_segundos(audio_path)
        if duracao_audio is None:
            raise _required_step_failure(
                service="ffmpeg",
                stage="generating_audio",
                code="narration_probe_failed",
                message=f"Não foi possível medir a narração da cena {shot.shot_number}.",
            )
        return NarrationClip(text=texto, audio_path=Path(audio_path), duration_seconds=duracao_audio)

    if progress_cb:
        progress_cb("generating_audio", "Gerando e medindo as narrações...")
    narracao = fit_narration_to_budget(
        [shot.narration_text_pt for shot in plan.shots],
        [shot.duration_seconds for shot in plan.shots],
        budget_seconds=request.duration_seconds - card_duration,
        duration_range=_faixa_de_duracao(model_config),
        synthesize=sintetizar_narracao,
    )
    aviso_roteiro = budget_warning(
        narracao,
        ceiling_seconds=request.duration_seconds,
        reserved_seconds=card_duration,
        available_ceilings=get_args(DurationLiteral),
    )
    if aviso_roteiro:
        warnings.append(aviso_roteiro)

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
            duracao=narracao.shot_durations[shot_index],
            output_path=f"{base_path}.mp4",
            reference_image_url=reference_image_url if should_use_reference else None,
            extra_arguments=model_config.default_arguments,
        )
        if not video_path:
            raise RuntimeError(
                f"Falha na geração da cena {shot.shot_number} usando {model_config.label}."
            )

        current_video_path = Path(video_path)

        clip = narracao.clips[shot_index]
        if clip is not None:
            combined_path = combinar_video_audio(
                current_video_path,
                clip.audio_path,
                f"{base_path}_combined.mp4",
            )
            if not combined_path:
                raise _required_step_failure(
                    service="ffmpeg",
                    stage="composing_audio",
                    code="audio_composition_failed",
                    message=f"Falha ao combinar a narração da cena {shot.shot_number}.",
                )
            current_video_path = Path(combined_path)

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

    for image_path, largura_exibida in _imagens_da_marca(
        plan,
        largura_video=largura,
        produto_overlay_path=produto_overlay_path,
        logo_path=logo_path_to_use,
        card_image_path=card_image_path,
    ).items():
        rotulo = "logo" if ref_logo_path and image_path == Path(ref_logo_path) else "embalagem"
        warnings.extend(_avisos_qualidade_imagem(rotulo, image_path, largura_exibida))

    if card_image_path:
        if progress_cb:
            progress_cb("composing", "Gerando card final com a logo da marca...")
        card_final_path = final_dir / "card_final_logo.mp4"
        card_video = gerar_card_logo(
            card_final_path,
            card_image_path,
            duracao=BRAND_CARD_DURATION_SECONDS,
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
        duracao_card_final=card_duration,
    )
    if not final_video:
        raise _required_step_failure(
            service="ffmpeg",
            stage="composing",
            code="final_video_invalid",
            message="Falha na composição ou validação do vídeo final.",
        )

    if progress_cb:
        progress_cb("uploading_drive", "Tentando enviar o vídeo final para o Google Drive...")
    drive_result = upload_para_drive(final_video)
    if not drive_result and JW_DRIVE_REQUIRED:
        raise _required_step_failure(
            service="google_drive",
            stage="uploading_drive",
            code="drive_upload_failed",
            message="Falha ao entregar o vídeo final no Google Drive.",
            render_confirmed=True,
        )
    if not drive_result:
        warnings.append(
            "Google Drive indisponível; o vídeo permanece disponível para download pelo Studio."
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
