import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.compositor import (
    CARD_BACKGROUND_DARK,
    CARD_BACKGROUND_LIGHT,
    brilho_da_marca,
    cor_de_fundo_do_cartao,
)

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _mark(tmp_path: Path, name: str, source: str) -> Path:
    path = tmp_path / name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source, "-frames:v", "1", str(path)], check=True)
    return path


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "color=white@0.0:s=200x100,format=rgba,drawbox=x=20:y=20:w=160:h=60:color=white@1.0:t=fill:replace=1",
            CARD_BACKGROUND_DARK,
        ),
        (
            "color=white@0.0:s=200x100,format=rgba,drawbox=x=20:y=20:w=160:h=60:color=black@1.0:t=fill:replace=1",
            CARD_BACKGROUND_LIGHT,
        ),
        ("color=black:s=200x100,format=rgba,drawbox=x=60:y=40:w=80:h=20:color=white:t=fill", CARD_BACKGROUND_LIGHT),
    ],
)
def test_card_background_contrasts_with_the_mark(tmp_path: Path, source: str, expected: str) -> None:
    assert cor_de_fundo_do_cartao(_mark(tmp_path, "marca.png", source)) == expected


def test_light_mark_brightness_ignores_transparent_pixels(tmp_path: Path) -> None:
    mark = _mark(
        tmp_path,
        "marca.png",
        "color=white@0.0:s=200x100,format=rgba,drawbox=x=90:y=40:w=20:h=20:color=white@1.0:t=fill:replace=1",
    )

    assert brilho_da_marca(mark) == pytest.approx(1.0, abs=0.05)


def test_fully_transparent_or_unreadable_mark_keeps_the_light_card(tmp_path: Path) -> None:
    empty = _mark(tmp_path, "vazia.png", "color=white@0.0:s=64x64,format=rgba")
    broken = tmp_path / "quebrada.png"
    broken.write_bytes(b"not an image")

    assert cor_de_fundo_do_cartao(empty) == CARD_BACKGROUND_LIGHT
    assert cor_de_fundo_do_cartao(broken) == CARD_BACKGROUND_LIGHT
