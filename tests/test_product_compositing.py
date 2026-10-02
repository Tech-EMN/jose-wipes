import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.compositor import compor_produto_em_cena, ganho_do_produto

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

WIDTH = 1080
HEIGHT = 1920
SCENE_COLOR = (32, 48, 64)


def _make(path: Path, source: str) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source, "-frames:v", "1", str(path)], check=True)
    return path


def _pixel(image: Path, x: int, y: int) -> tuple[int, int, int]:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(image), "-vf", f"crop=1:1:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True,
        capture_output=True,
    ).stdout
    return raw[0], raw[1], raw[2]


def _dimensions(image: Path) -> tuple[int, int]:
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(image)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    width, height = output.split(",")
    return int(width), int(height)


@pytest.fixture
def scene_and_product(tmp_path: Path) -> tuple[Path, Path]:
    scene = _make(tmp_path / "cena.png", "color=0x203040:s=1152x2048")
    product = _make(
        tmp_path / "produto.png",
        "color=white@0.0:s=400x200,format=rgba,drawbox=x=50:y=25:w=300:h=150:color=white@1.0:t=fill:replace=1",
    )
    return scene, product


def test_package_rests_on_the_surface_without_a_white_box(tmp_path: Path, scene_and_product) -> None:
    scene, product = scene_and_product

    output = compor_produto_em_cena(
        scene, tmp_path / "composta.png", product, posicao="centro_inferior", tamanho_pct=50, largura=WIDTH, altura=HEIGHT
    )

    assert output == tmp_path / "composta.png"
    assert _dimensions(output) == (WIDTH, HEIGHT)
    package_center = _pixel(output, 540, 1516)
    transparent_margin = _pixel(output, 290, 1516)
    under_package = _pixel(output, 540, 1660)
    far_from_package = _pixel(output, 100, 300)
    assert min(package_center) > 190
    assert max(package_center) < 250
    assert all(abs(a - b) <= 6 for a, b in zip(transparent_margin, far_from_package))
    assert sum(under_package) < sum(far_from_package)


@pytest.mark.parametrize(("luma", "expected"), [(0.0, 0.8), (0.17, 0.835), (0.5, 1.0), (0.9, 1.05)])
def test_package_brightness_follows_the_scene(luma: float, expected: float) -> None:
    assert ganho_do_produto(luma) == pytest.approx(expected)


def test_missing_product_image_returns_none(tmp_path: Path, scene_and_product) -> None:
    scene, _ = scene_and_product

    assert compor_produto_em_cena(
        scene, tmp_path / "x.png", tmp_path / "nao_existe.png", posicao="centro", tamanho_pct=50, largura=WIDTH, altura=HEIGHT
    ) is None
