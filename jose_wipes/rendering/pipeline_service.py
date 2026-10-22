"""Render planned José Wipes videos inside isolated job folders."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar, get_args

from jose_wipes.composition.compositor import (
    BRAND_CARD_LOGO_WIDTH_PCT,
    LOGO_OVERLAY_WIDTH_PCT,
    adicionar_logo_overlay,
    adicionar_texto_overlay,
    compor_video_final,
    cor_de_fundo_do_cartao,
    gerar_card_logo,
    imagem_tem_transparencia,
    obter_formato_imagem,
    overlay_produto,
)
from jose_wipes.config import (
    JW_DRIVE_REQUIRED,
    obter_path_imagem_produto,
    obter_url_imagem_produto,
)
from jose_wipes.composition.product_reference import prompt_pede_referencia_produto
from jose_wipes.integrations.gerador_midia import (
    combinar_video_audio,
    gerar_audio_elevenlabs,
    gerar_video_higgsfield,
    medir_duracao_segundos,
)
from jose_wipes.integrations.higgsfield_model_profiles import ModelArgumentProfile, find_argument_profile
from jose_wipes.integrations.errors import IntegrationFailure
from jose_wipes.integrations.higgsfield_utils import upload_higgsfield_file
from jose_wipes.integrations.uploader import upload_para_drive
from jose_wipes.model_registry import VideoModelConfig
from jose_wipes.rendering.checkpoints import RenderCheckpoints, RenderStage
from jose_wipes.result import Err, Ok, Result
from jose_wipes.composition.product_scene import (
    KeyframeSpec,
    animation_prompt,
    render_product_keyframe,
    shot_integrates_product,
)
from jose_wipes.planning.narration_plan import (
    BRAND_CARD_DURATION_SECONDS,
    DurationRange,
    NarrationClip,
    budget_warning,
    fit_narration_to_budget,
)
from jose_wipes.schemas import CreateJobRequest, DurationLiteral, PlannerOutput, PlannerShot


ProgressCallback = Callable[[str, str], None]
T = TypeVar("T")
DEFAULT_SHOT_DURATION_RANGE = DurationRange(min_seconds=3, max_seconds=15)


TEXT_POSITION_DEFAULT = "centro_inferior"
TEXT_POSITION_ABOVE_PRODUCT = "topo"


def _posicao_do_texto(shot: PlannerShot) -> str:
    if shot.product_overlay.ativo and shot.product_overlay.posicao == TEXT_POSITION_DEFAULT:
        return TEXT_POSITION_ABOVE_PRODUCT
    return TEXT_POSITION_DEFAULT


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

    from jose_wipes.integrations.video_generator import (
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


def _gerar_cena_com_produto_integrado(
    shot: PlannerShot,
    image_model: VideoModelConfig,
    *,
    produto_path: Path,
    aspecto: str,
    resolucao: str,
    largura: int,
    altura: int,
    duracao: int,
    base_path: Path,
) -> Path:
    keyframe_path = render_product_keyframe(
        KeyframeSpec(
            prompt=shot.visual_prompt_en,
            aspect_ratio=aspecto,
            width=largura,
            height=altura,
            product_path=produto_path,
            position=shot.product_overlay.posicao,
            size_pct=shot.product_overlay.tamanho_pct,
            output_dir=base_path.parent,
            name=base_path.name,
        )
    )
    keyframe_url = _upload_reference_image(keyframe_path)
    if not keyframe_url:
        raise IntegrationFailure(
            service="higgsfield",
            stage="uploading_keyframe",
            code="keyframe_upload_failed",
            user_message="Não foi possível enviar a imagem-base da cena com produto.",
            technical_message=f"upload failed for {keyframe_path}",
        )
    video_path = _gerar_video_com_fallback(
        image_model,
        animation_prompt(shot.visual_prompt_en),
        aspecto=aspecto,
        resolucao=resolucao,
        duracao=duracao,
        output_path=f"{base_path}.mp4",
        reference_image_url=keyframe_url,
        extra_arguments=image_model.default_arguments,
    )
    if not video_path:
        raise IntegrationFailure(
            service="higgsfield",
            stage="generating",
            code="no_output",
            user_message="A Higgsfield não entregou a cena com produto.",
            technical_message=f"{image_model.application} returned no video",
        )
    return Path(video_path)


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


MANIFEST_FILENAME = "manifesto_render.json"
STUDIO_SERVICE = "studio"
RESUMING_STEP = "resuming"


@dataclass(frozen=True)
class RenderInputs:
    job_dir: Path
    request: CreateJobRequest
    plan: PlannerOutput
    model_config: VideoModelConfig
    ref_embalagem_path: str | None = None
    ref_logo_path: str | None = None
    apply_logo_overlay: bool = True
    use_product_reference: bool = True


@dataclass(frozen=True)
class RenderPlan:
    inputs: RenderInputs
    model_config: VideoModelConfig
    image_model: VideoModelConfig | None
    scenes_dir: Path
    final_dir: Path
    aspect_ratio: str
    width: int
    height: int
    reference_image_url: str | None
    shot_reference_flags: tuple[bool, ...]
    logo_path: Path | None
    product_overlay_path: Path | None
    scene_product_path: Path | None
    card_image_path: Path | None
    card_duration: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ShotMedia:
    shot: PlannerShot
    base_path: Path
    video_path: Path
    narration: NarrationClip | None
    product_integrated: bool


@dataclass(frozen=True)
class GeneratedMedia:
    shots: tuple[ShotMedia, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ComposedVideo:
    final_video_path: Path
    scene_paths: tuple[Path, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PublishedVideo:
    drive_result: dict[str, object] | None
    warnings: tuple[str, ...]


def _report(progress_cb: ProgressCallback | None, step: str, message: str) -> None:
    if progress_cb:
        progress_cb(step, message)


def _capture(step: Callable[[], T]) -> Result[T]:
    try:
        return Ok(step())
    except IntegrationFailure as failure:
        return Err(failure)


def _resolution_not_supported(model_config: VideoModelConfig, resolution: str) -> IntegrationFailure:
    message = f"Resolução {resolution} não é suportada pelo modelo {model_config.label}."
    return IntegrationFailure(
        service=STUDIO_SERVICE,
        stage="planning_render",
        code="resolution_not_supported",
        user_message=message,
        technical_message=message,
        retryable=False,
        reason="resolution_not_supported",
    )


def _product_reference_url(
    ref_embalagem_path: str | None,
    warnings: list[str],
    progress_cb: ProgressCallback | None,
) -> str | None:
    if ref_embalagem_path:
        _report(progress_cb, "uploading_ref", "Enviando imagem da embalagem como referência...")
        uploaded_url = _upload_reference_image(ref_embalagem_path)
        if uploaded_url:
            return uploaded_url
        warnings.append("Não foi possível enviar a embalagem do usuário; usando padrão.")
    try:
        return obter_url_imagem_produto()
    except Exception as exc:
        warnings.append(f"Referência visual do produto indisponível: {exc}")
        return None


def _existing_path(candidate: str | None) -> Path | None:
    if candidate and Path(candidate).exists():
        return Path(candidate)
    return None


def plan_render(
    inputs: RenderInputs,
    progress_cb: ProgressCallback | None = None,
) -> Result[RenderPlan]:
    """Resolve the model, dimensions and brand references the other stages depend on."""

    request = inputs.request
    if request.resolution not in inputs.model_config.allowed_resolutions:
        return Err(_resolution_not_supported(inputs.model_config, request.resolution))

    def build() -> RenderPlan:
        warnings: list[str] = []
        model_config = inputs.model_config.for_resolution(request.resolution)
        if model_config.application != inputs.model_config.application:
            warnings.append(
                f"Em {request.resolution}, o nível {inputs.model_config.tier} gera com {model_config.application}, "
                f"porque {inputs.model_config.application} não entrega essa resolução de forma nativa."
            )

        shot_reference_flags = tuple(
            inputs.use_product_reference
            and not shot.product_overlay.ativo
            and prompt_pede_referencia_produto(
                shot.visual_prompt_en,
                shot.narration_text_pt,
                shot.overlay_text,
                shot.notes,
            )
            for shot in inputs.plan.shots
        )
        reference_image_url = (
            _product_reference_url(inputs.ref_embalagem_path, warnings, progress_cb)
            if any(shot_reference_flags)
            else None
        )

        product_overlay_path = _existing_path(inputs.ref_embalagem_path)
        default_product = obter_path_imagem_produto()
        card_image_path = _imagem_do_cartao(inputs.ref_logo_path, inputs.ref_embalagem_path)
        width, height = VIDEO_DIMENSIONS[(request.orientation, request.resolution)]
        scenes_dir = inputs.job_dir / "cenas"
        final_dir = inputs.job_dir / "final"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        return RenderPlan(
            inputs=inputs,
            model_config=model_config,
            image_model=model_config.image_to_video(),
            scenes_dir=scenes_dir,
            final_dir=final_dir,
            aspect_ratio=ASPECT_RATIO_BY_ORIENTATION[request.orientation],
            width=width,
            height=height,
            reference_image_url=reference_image_url,
            shot_reference_flags=shot_reference_flags,
            logo_path=_existing_path(inputs.ref_logo_path) if inputs.apply_logo_overlay else None,
            product_overlay_path=product_overlay_path,
            scene_product_path=product_overlay_path or (Path(default_product) if default_product else None),
            card_image_path=card_image_path,
            card_duration=BRAND_CARD_DURATION_SECONDS if card_image_path else 0,
            warnings=tuple(warnings),
        )

    return _capture(build)


def _synthesize_narration(render_plan: RenderPlan) -> Callable[[int, str], NarrationClip]:
    def synthesize(shot_index: int, texto: str) -> NarrationClip:
        shot = render_plan.inputs.plan.shots[shot_index]
        audio_path = gerar_audio_elevenlabs(
            shot.voice_persona,
            texto,
            f"{render_plan.scenes_dir / f'shot_{shot.shot_number:02d}'}_audio.mp3",
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

    return synthesize


def _generate_shot_video(
    render_plan: RenderPlan,
    shot_index: int,
    duration: int,
    warnings: list[str],
    progress_cb: ProgressCallback | None,
) -> tuple[Path, bool]:
    shot = render_plan.inputs.plan.shots[shot_index]
    title = render_plan.inputs.plan.title
    total_shots = len(render_plan.inputs.plan.shots)
    base_path = render_plan.scenes_dir / f"shot_{shot.shot_number:02d}"
    product_path = render_plan.scene_product_path
    integrates_product = (
        render_plan.image_model is not None
        and product_path is not None
        and product_path.exists()
        and shot_integrates_product(shot)
    )
    if integrates_product:
        _report(
            progress_cb,
            "generating",
            f"Gerando cena {shot.shot_number}/{total_shots} com a embalagem na cena: {title}",
        )
        try:
            return (
                _gerar_cena_com_produto_integrado(
                    shot,
                    render_plan.image_model,
                    produto_path=product_path,
                    aspecto=render_plan.aspect_ratio,
                    resolucao=render_plan.inputs.request.resolution,
                    largura=render_plan.width,
                    altura=render_plan.height,
                    duracao=duration,
                    base_path=base_path,
                ),
                True,
            )
        except IntegrationFailure as failure:
            warnings.append(
                f"Cena {shot.shot_number}: não foi possível colocar a embalagem dentro da cena "
                f"({failure.code}); ela foi sobreposta ao vídeo."
            )

    video_path = _gerar_video_com_fallback(
        render_plan.model_config,
        shot.visual_prompt_en,
        aspecto=render_plan.aspect_ratio,
        resolucao=render_plan.inputs.request.resolution,
        duracao=duration,
        output_path=f"{base_path}.mp4",
        reference_image_url=(
            render_plan.reference_image_url if render_plan.shot_reference_flags[shot_index] else None
        ),
        extra_arguments=render_plan.model_config.default_arguments,
    )
    if not video_path:
        raise _required_step_failure(
            service="higgsfield",
            stage="generating",
            code="scene_generation_failed",
            message=f"Falha na geração da cena {shot.shot_number} usando {render_plan.model_config.label}.",
        )
    return Path(video_path), False


def generate_media(
    render_plan: RenderPlan,
    progress_cb: ProgressCallback | None = None,
) -> Result[GeneratedMedia]:
    """Synthesize the narration and generate the raw video of every shot."""

    def build() -> GeneratedMedia:
        plan = render_plan.inputs.plan
        request = render_plan.inputs.request
        warnings: list[str] = []

        _report(progress_cb, "generating_audio", "Gerando e medindo as narrações...")
        narration = fit_narration_to_budget(
            [shot.narration_text_pt for shot in plan.shots],
            [shot.duration_seconds for shot in plan.shots],
            budget_seconds=request.duration_seconds - render_plan.card_duration,
            duration_range=_faixa_de_duracao(render_plan.model_config),
            synthesize=_synthesize_narration(render_plan),
        )
        script_warning = budget_warning(
            narration,
            ceiling_seconds=request.duration_seconds,
            reserved_seconds=render_plan.card_duration,
            available_ceilings=get_args(DurationLiteral),
        )
        if script_warning:
            warnings.append(script_warning)

        shots: list[ShotMedia] = []
        for shot_index, shot in enumerate(plan.shots):
            _report(
                progress_cb,
                "generating",
                f"Gerando cena {shot.shot_number}/{len(plan.shots)}: {plan.title}",
            )
            video_path, product_integrated = _generate_shot_video(
                render_plan,
                shot_index,
                narration.shot_durations[shot_index],
                warnings,
                progress_cb,
            )
            shots.append(
                ShotMedia(
                    shot=shot,
                    base_path=render_plan.scenes_dir / f"shot_{shot.shot_number:02d}",
                    video_path=video_path,
                    narration=narration.clips[shot_index],
                    product_integrated=product_integrated,
                )
            )
        return GeneratedMedia(shots=tuple(shots), warnings=tuple(warnings))

    return _capture(build)


def _compose_shot(render_plan: RenderPlan, media: ShotMedia) -> Path:
    shot = media.shot
    current_video_path = media.video_path

    if media.narration is not None:
        combined_path = combinar_video_audio(
            current_video_path,
            media.narration.audio_path,
            f"{media.base_path}_combined.mp4",
        )
        if not combined_path:
            raise _required_step_failure(
                service="ffmpeg",
                stage="composing_audio",
                code="audio_composition_failed",
                message=f"Falha ao combinar a narração da cena {shot.shot_number}.",
            )
        current_video_path = Path(combined_path)

    if shot.product_overlay.ativo and not media.product_integrated:
        overlay_path = overlay_produto(
            current_video_path,
            f"{media.base_path}_produto.mp4",
            produto_path=render_plan.product_overlay_path,
            posicao=shot.product_overlay.posicao,
            tamanho_pct=shot.product_overlay.tamanho_pct,
            inicio_seg=shot.product_overlay.inicio_seg,
        )
        if not overlay_path:
            raise _required_step_failure(
                service="ffmpeg",
                stage="composing",
                code="product_overlay_failed",
                message=f"Falha ao aplicar a embalagem na cena {shot.shot_number}.",
            )
        current_video_path = Path(overlay_path)

    if shot.overlay_text:
        text_path = adicionar_texto_overlay(
            current_video_path,
            shot.overlay_text,
            f"{media.base_path}_texto.mp4",
            _posicao_do_texto(shot),
        )
        if not text_path:
            raise _required_step_failure(
                service="ffmpeg",
                stage="composing",
                code="text_overlay_failed",
                message=f"Falha ao aplicar o texto da cena {shot.shot_number}.",
            )
        current_video_path = Path(text_path)

    return current_video_path


def _brand_image_warnings(render_plan: RenderPlan) -> list[str]:
    ref_logo_path = render_plan.inputs.ref_logo_path
    warnings: list[str] = []
    for image_path, largura_exibida in _imagens_da_marca(
        render_plan.inputs.plan,
        largura_video=render_plan.width,
        produto_overlay_path=render_plan.product_overlay_path,
        logo_path=render_plan.logo_path,
        card_image_path=render_plan.card_image_path,
    ).items():
        rotulo = "logo" if ref_logo_path and image_path == Path(ref_logo_path) else "embalagem"
        warnings.extend(_avisos_qualidade_imagem(rotulo, image_path, largura_exibida))
    return warnings


def _render_brand_card(render_plan: RenderPlan, card_image_path: Path) -> Path:
    card_video = gerar_card_logo(
        render_plan.final_dir / "card_final_logo.mp4",
        card_image_path,
        duracao=BRAND_CARD_DURATION_SECONDS,
        largura=render_plan.width,
        altura=render_plan.height,
        fundo=cor_de_fundo_do_cartao(card_image_path),
    )
    if not card_video:
        raise _required_step_failure(
            service="ffmpeg",
            stage="composing",
            code="brand_card_failed",
            message="Falha ao gerar o card final da marca.",
        )
    return Path(card_video)


def compose_video(
    render_plan: RenderPlan,
    media: GeneratedMedia,
    progress_cb: ProgressCallback | None = None,
) -> Result[ComposedVideo]:
    """Add narration, product, text and brand card to the scenes and join them."""

    def build() -> ComposedVideo:
        scene_paths = [_compose_shot(render_plan, shot_media) for shot_media in media.shots]
        warnings = _brand_image_warnings(render_plan)

        if render_plan.card_image_path:
            _report(progress_cb, "composing", "Gerando card final com a logo da marca...")
            scene_paths.append(_render_brand_card(render_plan, render_plan.card_image_path))

        _report(progress_cb, "composing", "Compondo vídeo final e aplicando marca da empresa...")
        request = render_plan.inputs.request
        final_video = compor_video_final(
            [str(path) for path in scene_paths],
            render_plan.inputs.plan.title,
            render_plan.logo_path,
            largura=render_plan.width,
            altura=render_plan.height,
            output_dir=render_plan.final_dir,
            duracao_maxima=request.duration_seconds,
            duracao_card_final=render_plan.card_duration,
        )
        if not final_video:
            raise _required_step_failure(
                service="ffmpeg",
                stage="composing",
                code="final_video_invalid",
                message="Falha na composição ou validação do vídeo final.",
            )
        return ComposedVideo(
            final_video_path=Path(final_video),
            scene_paths=tuple(scene_paths),
            warnings=tuple(warnings),
        )

    return _capture(build)


def publish_video(
    composed: ComposedVideo,
    progress_cb: ProgressCallback | None = None,
) -> Result[PublishedVideo]:
    """Deliver the final video to Google Drive when it is configured."""

    _report(progress_cb, "uploading_drive", "Tentando enviar o vídeo final para o Google Drive...")
    drive_result = upload_para_drive(composed.final_video_path)
    if drive_result:
        return Ok(PublishedVideo(drive_result=drive_result, warnings=()))
    if JW_DRIVE_REQUIRED:
        return Err(
            _required_step_failure(
                service="google_drive",
                stage="uploading_drive",
                code="drive_upload_failed",
                message="Falha ao entregar o vídeo final no Google Drive.",
                render_confirmed=True,
            )
        )
    return Ok(
        PublishedVideo(
            drive_result=None,
            warnings=("Google Drive indisponível; o vídeo permanece disponível para download pelo Studio.",),
        )
    )


def _unwrap(
    result: Result[T],
    stage: RenderStage,
    checkpoints: RenderCheckpoints,
    to_output: Callable[[T], dict[str, object]] | None = None,
) -> T:
    if isinstance(result, Err):
        checkpoints.failed(stage, result.failure)
        raise result.failure
    checkpoints.completed(stage, to_output(result.value) if to_output else None)
    return result.value


def _media_to_output(media: GeneratedMedia) -> dict[str, object]:
    return {
        "shots": [
            {
                "shot_number": shot_media.shot.shot_number,
                "base_path": str(shot_media.base_path),
                "video_path": str(shot_media.video_path),
                "product_integrated": shot_media.product_integrated,
                "narration": (
                    {
                        "text": shot_media.narration.text,
                        "audio_path": str(shot_media.narration.audio_path),
                        "duration_seconds": shot_media.narration.duration_seconds,
                    }
                    if shot_media.narration
                    else None
                ),
            }
            for shot_media in media.shots
        ],
        "warnings": list(media.warnings),
    }


def _restore_narration(stored: object) -> NarrationClip | None:
    if not isinstance(stored, dict):
        return None
    return NarrationClip(
        text=str(stored["text"]),
        audio_path=Path(str(stored["audio_path"])),
        duration_seconds=float(stored["duration_seconds"]),
    )


def _restore_media(checkpoints: RenderCheckpoints, render_plan: RenderPlan) -> GeneratedMedia | None:
    output = checkpoints.output(RenderStage.GENERATE_MEDIA)
    if output is None:
        return None
    stored_shots = output.get("shots")
    plan_shots = render_plan.inputs.plan.shots
    if not isinstance(stored_shots, list) or len(stored_shots) != len(plan_shots):
        return None

    shots: list[ShotMedia] = []
    for shot, stored in zip(plan_shots, stored_shots):
        if not isinstance(stored, dict) or stored.get("shot_number") != shot.shot_number:
            return None
        narration = _restore_narration(stored.get("narration"))
        video_path = Path(str(stored["video_path"]))
        required_files = [video_path, *([narration.audio_path] if narration else [])]
        if not all(path.exists() for path in required_files):
            return None
        shots.append(
            ShotMedia(
                shot=shot,
                base_path=Path(str(stored["base_path"])),
                video_path=video_path,
                narration=narration,
                product_integrated=bool(stored.get("product_integrated")),
            )
        )
    return GeneratedMedia(shots=tuple(shots), warnings=tuple(output.get("warnings", [])))


def _composed_to_output(composed: ComposedVideo) -> dict[str, object]:
    return {
        "final_video_path": str(composed.final_video_path),
        "scene_paths": [str(path) for path in composed.scene_paths],
        "warnings": list(composed.warnings),
    }


def _restore_composed(checkpoints: RenderCheckpoints) -> ComposedVideo | None:
    output = checkpoints.output(RenderStage.COMPOSE)
    if output is None:
        return None
    final_video_path = Path(str(output["final_video_path"]))
    if not final_video_path.exists():
        return None
    return ComposedVideo(
        final_video_path=final_video_path,
        scene_paths=tuple(Path(str(path)) for path in output.get("scene_paths", [])),
        warnings=tuple(output.get("warnings", [])),
    )


def _media_for(
    render_plan: RenderPlan,
    checkpoints: RenderCheckpoints,
    progress_cb: ProgressCallback | None,
) -> tuple[GeneratedMedia, bool]:
    restored = _restore_media(checkpoints, render_plan)
    if restored is not None:
        _report(progress_cb, RESUMING_STEP, "Reaproveitando narrações e cenas já geradas...")
        return restored, True
    checkpoints.restart_from(RenderStage.GENERATE_MEDIA)
    media = _unwrap(
        generate_media(render_plan, progress_cb),
        RenderStage.GENERATE_MEDIA,
        checkpoints,
        _media_to_output,
    )
    return media, False


def _composed_for(
    render_plan: RenderPlan,
    media: GeneratedMedia,
    checkpoints: RenderCheckpoints,
    progress_cb: ProgressCallback | None,
    *,
    media_restored: bool,
) -> ComposedVideo:
    restored = _restore_composed(checkpoints) if media_restored else None
    if restored is not None:
        _report(progress_cb, RESUMING_STEP, "Reaproveitando o vídeo final já composto...")
        return restored
    checkpoints.restart_from(RenderStage.COMPOSE)
    return _unwrap(
        compose_video(render_plan, media, progress_cb),
        RenderStage.COMPOSE,
        checkpoints,
        _composed_to_output,
    )


def _write_manifest(
    render_plan: RenderPlan,
    composed: ComposedVideo,
    published: PublishedVideo,
    warnings: list[str],
) -> None:
    inputs = render_plan.inputs
    manifest = {
        "titulo": inputs.plan.title,
        "modelo_video": render_plan.model_config.label,
        "modelo_tier": render_plan.model_config.tier,
        "aspect_ratio": render_plan.aspect_ratio,
        "resolucao": inputs.request.resolution,
        "cenas": [str(path) for path in composed.scene_paths],
        "saida_final": str(composed.final_video_path),
        "google_drive": published.drive_result,
        "ref_embalagem_usada": inputs.ref_embalagem_path or "padrão",
        "ref_logo_usada": str(render_plan.logo_path) if render_plan.logo_path else "nenhuma",
        "logo_overlay_aplicado": inputs.apply_logo_overlay,
        "warnings": warnings,
    }
    (inputs.job_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


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
    """Run the render stages for one job, reusing the outputs a previous attempt completed."""

    inputs = RenderInputs(
        job_dir=job_dir,
        request=request,
        plan=plan,
        model_config=model_config,
        ref_embalagem_path=ref_embalagem_path,
        ref_logo_path=ref_logo_path,
        apply_logo_overlay=apply_logo_overlay,
        use_product_reference=use_product_reference,
    )
    checkpoints = RenderCheckpoints(job_dir)

    render_plan = _unwrap(plan_render(inputs, progress_cb), RenderStage.PLAN, checkpoints)
    media, media_restored = _media_for(render_plan, checkpoints, progress_cb)
    composed = _composed_for(
        render_plan,
        media,
        checkpoints,
        progress_cb,
        media_restored=media_restored,
    )
    checkpoints.restart_from(RenderStage.PUBLISH)
    published = _unwrap(publish_video(composed, progress_cb), RenderStage.PUBLISH, checkpoints)

    warnings = [
        *render_plan.warnings,
        *media.warnings,
        *composed.warnings,
        *published.warnings,
    ]
    _write_manifest(render_plan, composed, published, warnings)

    drive_result = published.drive_result
    return {
        "final_video_path": str(composed.final_video_path),
        "drive_file_id": drive_result.get("id") if drive_result else None,
        "drive_url": drive_result.get("link") if drive_result else None,
        "warnings": warnings,
    }
