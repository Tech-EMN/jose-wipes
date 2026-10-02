"""Place the real packaging inside a generated still so the video model animates it with the scene."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from scripts.compositor import compor_produto_em_cena
from scripts.gerador_midia import gerar_video_higgsfield
from scripts.higgsfield_model_profiles import SOUL_2_APPLICATION
from scripts.integration_errors import IntegrationFailure
from webapp.planner import PRODUCT_COMPOSITING_VISUAL_CONSTRAINT
from webapp.schemas import PlannerShot

KEYFRAME_RESOLUTION = "1080p"
EMPTY_AREA_SENTENCE = re.compile(r"Keep a clean empty [\w -]+? placement area on the primary surface\.\s*")
KEYFRAME_SURFACE_HINT = (
    "A flat surface spans the lower third of the frame in sharp focus, "
    "with an empty spot on it where an object will rest."
)
ANIMATION_CONSTRAINT = (
    "The white wet wipes package already resting on the surface stays exactly where it is, "
    "unchanged and fully visible; do not move, redraw, relabel, resize or cover it. "
    "Locked-off camera; motion comes only from the people and from subtle light changes."
)


@dataclass(frozen=True)
class KeyframeSpec:
    prompt: str
    aspect_ratio: str
    width: int
    height: int
    product_path: Path
    position: str
    size_pct: int
    output_dir: Path
    name: str


def keyframe_prompt(visual_prompt: str) -> str:
    return f"{visual_prompt.rstrip()} {KEYFRAME_SURFACE_HINT}"


def animation_prompt(visual_prompt: str) -> str:
    without_empty_area = EMPTY_AREA_SENTENCE.sub("", visual_prompt).replace(PRODUCT_COMPOSITING_VISUAL_CONSTRAINT, "")
    return f"{' '.join(without_empty_area.split())} {ANIMATION_CONSTRAINT}"


def shot_integrates_product(shot: PlannerShot) -> bool:
    return shot.product_overlay.ativo and not shot.product_overlay.inicio_seg


def render_product_keyframe(spec: KeyframeSpec) -> Path:
    still_path = gerar_video_higgsfield(
        SOUL_2_APPLICATION,
        keyframe_prompt(spec.prompt),
        aspecto=spec.aspect_ratio,
        resolucao=KEYFRAME_RESOLUTION,
        output_path=str(spec.output_dir / f"{spec.name}_cena.png"),
        raise_on_failure=True,
        max_retries=0,
    )
    if not still_path:
        raise IntegrationFailure(
            service="higgsfield",
            stage="generating_keyframe",
            code="keyframe_failed",
            user_message="A Higgsfield não gerou a imagem-base da cena com produto.",
            technical_message=f"{SOUL_2_APPLICATION} returned no image",
        )

    composed_path = compor_produto_em_cena(
        still_path,
        spec.output_dir / f"{spec.name}_cena_produto.png",
        spec.product_path,
        posicao=spec.position,
        tamanho_pct=spec.size_pct,
        largura=spec.width,
        altura=spec.height,
    )
    if composed_path is None:
        raise IntegrationFailure(
            service="ffmpeg",
            stage="composing_keyframe",
            code="keyframe_composition_failed",
            user_message="Não foi possível colocar a embalagem na imagem-base da cena.",
            technical_message=f"compor_produto_em_cena failed for {still_path}",
        )
    return Path(composed_path)
