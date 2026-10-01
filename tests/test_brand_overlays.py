import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.compositor import (
    adicionar_logo_overlay,
    compor_produto_na_imagem,
    imagem_tem_transparencia,
    obter_formato_imagem,
)
from webapp.pipeline_service import _avisos_qualidade_imagem, _imagens_da_marca
from webapp.schemas import PlannerOutput, PlannerShot, ProductOverlayConfig

FFPROBE_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _filter_complex(subprocess_mock) -> str:
    command = subprocess_mock.call_args.args[0]
    return command[command.index("-filter_complex") + 1]


@pytest.mark.parametrize(
    ("video_dimensions", "expected_scale"),
    [((1080, 1920), "scale=162:-1"), ((720, 1280), "scale=108:-1")],
)
def test_logo_watermark_scales_with_video_width(tmp_path: Path, video_dimensions, expected_scale) -> None:
    video_path = tmp_path / "video.mp4"
    logo_path = tmp_path / "logo.png"
    video_path.write_bytes(b"video")
    logo_path.write_bytes(b"logo")

    with patch("scripts.compositor._obter_dimensoes_video", return_value=video_dimensions), patch(
        "scripts.compositor._subprocess_run"
    ) as subprocess_mock:
        adicionar_logo_overlay(video_path, logo_path, tmp_path / "out.mp4")

    assert f"[1:v]{expected_scale}" in _filter_complex(subprocess_mock)


def test_logo_watermark_is_skipped_when_video_cannot_be_measured(tmp_path: Path) -> None:
    video_path = tmp_path / "video.mp4"
    logo_path = tmp_path / "logo.png"
    output_path = tmp_path / "out.mp4"
    video_path.write_bytes(b"video")
    logo_path.write_bytes(b"logo")

    with patch("scripts.compositor._obter_dimensoes_video", return_value=None), patch(
        "scripts.compositor._subprocess_run"
    ) as subprocess_mock:
        result = adicionar_logo_overlay(video_path, logo_path, output_path)

    subprocess_mock.assert_not_called()
    assert result == output_path
    assert output_path.read_bytes() == b"video"


def test_product_in_scene_image_scales_with_scene_width(tmp_path: Path) -> None:
    scene_path = tmp_path / "scene.png"
    product_path = tmp_path / "product.png"
    scene_path.write_bytes(b"scene")
    product_path.write_bytes(b"product")

    with patch("scripts.compositor._obter_dimensoes_video", return_value=(1080, 1920)), patch(
        "scripts.compositor._subprocess_run"
    ) as subprocess_mock:
        compor_produto_na_imagem(scene_path, tmp_path / "out.png", produto_path=product_path, tamanho_pct=30)

    assert "[1:v]scale=324:-1[prod]" in _filter_complex(subprocess_mock)


@pytest.mark.parametrize(
    ("pix_fmt", "transparent"),
    [("rgba", True), ("ya8", True), ("yuva420p", True), ("pal8", True), ("rgb24", False), ("yuvj420p", False)],
)
def test_transparency_is_detected_by_pixel_format(pix_fmt: str, transparent: bool) -> None:
    assert imagem_tem_transparencia(pix_fmt) is transparent


@pytest.mark.skipif(not FFPROBE_AVAILABLE, reason="ffmpeg/ffprobe indisponível")
def test_image_format_is_read_with_ffprobe(tmp_path: Path) -> None:
    png_path = tmp_path / "logo.png"
    jpg_path = tmp_path / "logo.jpg"
    for source, path in (("color=c=red@0.5:s=300x200,format=rgba", png_path), ("color=c=red:s=640x480", jpg_path)):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", source, "-frames:v", "1", str(path)],
            check=True,
        )

    png_width, png_pix_fmt = obter_formato_imagem(png_path)
    jpg_width, jpg_pix_fmt = obter_formato_imagem(jpg_path)

    assert (png_width, imagem_tem_transparencia(png_pix_fmt)) == (300, True)
    assert (jpg_width, imagem_tem_transparencia(jpg_pix_fmt)) == (640, False)


def test_unreadable_image_format_returns_none(tmp_path: Path) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")

    assert obter_formato_imagem(broken) is None


@pytest.mark.parametrize(
    ("formato", "expected_count", "expected_fragments"),
    [
        ((2000, "rgba"), 0, []),
        ((2000, "rgb24"), 1, ["não tem fundo transparente"]),
        ((677, "rgba"), 1, ["677px", "864px"]),
        ((400, "yuvj420p"), 2, ["não tem fundo transparente", "400px"]),
    ],
)
def test_brand_image_quality_warnings(tmp_path: Path, formato, expected_count, expected_fragments) -> None:
    with patch("webapp.pipeline_service.obter_formato_imagem", return_value=formato):
        avisos = _avisos_qualidade_imagem("embalagem", tmp_path / "embalagem.png", 864)

    assert len(avisos) == expected_count
    for fragment in expected_fragments:
        assert any(fragment in aviso for aviso in avisos)


def test_unanalyzable_brand_image_is_reported(tmp_path: Path) -> None:
    with patch("webapp.pipeline_service.obter_formato_imagem", return_value=None):
        avisos = _avisos_qualidade_imagem("logo", tmp_path / "logo.png", 162)

    assert avisos == ["Não foi possível analisar a imagem de logo (logo.png)."]


def _plan(*overlay_sizes: int | None) -> PlannerOutput:
    return PlannerOutput(
        title="Jose Wipes",
        enhanced_brief_pt="Brief.",
        global_style="Estilo.",
        final_cta_pt="CTA.",
        shots=[
            PlannerShot(
                shot_number=index,
                visual_prompt_en="A quiet gym locker room after training.",
                product_overlay=ProductOverlayConfig(ativo=size is not None, tamanho_pct=size or 50),
            )
            for index, size in enumerate(overlay_sizes, start=1)
        ],
    )


def test_brand_images_use_largest_displayed_width(tmp_path: Path) -> None:
    embalagem = tmp_path / "embalagem.png"
    logo = tmp_path / "logo.png"

    exibicoes = _imagens_da_marca(
        _plan(45, 55, None),
        largura_video=1080,
        produto_overlay_path=embalagem,
        logo_path=logo,
        card_image_path=logo,
    )

    assert exibicoes == {embalagem: 594, logo: 864}


def test_default_product_is_checked_only_when_an_overlay_is_used(tmp_path: Path) -> None:
    default_product = tmp_path / "default.png"

    with patch("webapp.pipeline_service.obter_path_imagem_produto", return_value=default_product):
        with_overlay = _imagens_da_marca(
            _plan(50), largura_video=720, produto_overlay_path=None, logo_path=None, card_image_path=None
        )
        without_overlay = _imagens_da_marca(
            _plan(None), largura_video=720, produto_overlay_path=None, logo_path=None, card_image_path=None
        )

    assert with_overlay == {default_product: 360}
    assert without_overlay == {}
