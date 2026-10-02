import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.compositor import adicionar_texto_overlay, quebrar_texto_overlay
from webapp.pipeline_service import _posicao_do_texto
from webapp.schemas import PlannerShot, ProductOverlayConfig

LONG_TEXT = "Sem fragrância. Sem cheirinho. Apenas para homens que levam a limpeza a sério: 100% José Wipes!"
EDGE_COLUMNS = 24
BRIGHT_LEVEL = 200

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.mark.parametrize("width", [720, 1080, 1920])
def test_long_text_is_wrapped_to_fit_the_frame(width: int) -> None:
    lines = quebrar_texto_overlay(LONG_TEXT, width).splitlines()

    assert len(lines) > 1
    assert " ".join(lines) == " ".join(LONG_TEXT.split())
    assert max(len(line) for line in lines) <= 35


def _black_video(path: Path, width: int, height: int) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={width}x{height}:d=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )


def _edge_brightness(path: Path, width: int, height: int) -> int:
    frame = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True,
        capture_output=True,
    ).stdout
    rows = [frame[row * width:(row + 1) * width] for row in range(height // 2, height)]
    return max(max(row[:EDGE_COLUMNS]) for row in rows) if rows else 0


@needs_ffmpeg
@pytest.mark.parametrize(("width", "height"), [(1080, 1920), (720, 1280)])
def test_rendered_text_with_special_characters_stays_inside_the_frame(tmp_path: Path, width: int, height: int) -> None:
    source = tmp_path / "source.mp4"
    _black_video(source, width, height)

    output = adicionar_texto_overlay(source, LONG_TEXT, tmp_path / "texto.mp4")

    assert output == tmp_path / "texto.mp4"
    assert output.exists()
    assert not (tmp_path / "texto.txt").exists()
    assert _edge_brightness(output, width, height) < BRIGHT_LEVEL


@pytest.mark.parametrize(
    ("active", "position", "expected"),
    [(True, "centro_inferior", "topo"), (True, "centro", "centro_inferior"), (False, "centro_inferior", "centro_inferior")],
)
def test_caption_moves_to_the_top_when_the_product_sits_at_the_bottom(active: bool, position: str, expected: str) -> None:
    shot = PlannerShot(
        shot_number=1,
        visual_prompt_en="An empty premium studio scene with soft light.",
        product_overlay=ProductOverlayConfig(ativo=active, posicao=position),
    )

    assert _posicao_do_texto(shot) == expected
