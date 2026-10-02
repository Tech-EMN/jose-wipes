import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from webapp.reference_images import TransparencyCheck, check_transparency

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

API_KEY = "test-key"
FORM = {
    "resolution": "720p",
    "orientation": "vertical",
    "duration_seconds": "10",
    "prompt": "Anuncio de teste",
    "video_model": "kling_3_0",
}


def _image(tmp_path: Path, name: str, color: str) -> bytes:
    path = tmp_path / name
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color={color}:s=64x64,format=rgba",
         "-frames:v", "1", str(path)],
        check=True,
    )
    return path.read_bytes()


@pytest.mark.parametrize(
    ("name", "color", "expected"),
    [
        ("sem_fundo.png", "white@0.0", TransparencyCheck.TRANSPARENT),
        ("rgba_opaco.png", "white", TransparencyCheck.OPAQUE),
        ("foto.jpg", "white", TransparencyCheck.OPAQUE),
    ],
)
def test_transparency_check_reads_real_pixels(tmp_path: Path, name: str, color: str, expected) -> None:
    assert check_transparency(_image(tmp_path, name, color), name) is expected


def test_unreadable_upload_is_reported() -> None:
    assert check_transparency(b"not an image", "logo.png") is TransparencyCheck.UNREADABLE


@pytest.fixture
def client_and_manager():
    from webapp import main

    manager = MagicMock()
    manager.create_job.return_value = {"job_id": "a" * 32}
    manager.get_job_status.return_value = MagicMock(job_id="a" * 32, status="queued", download_url=None)
    with patch.object(main, "job_manager", manager), patch("webapp.auth.API_KEY", API_KEY), patch(
        "webapp.main.moderate_prompt_sync", return_value=MagicMock(allowed=True)
    ):
        yield TestClient(main.app, headers={"X-API-Key": API_KEY}), manager


@pytest.mark.parametrize("field", ["ref_embalagem", "ref_logo"])
def test_opaque_brand_images_are_rejected_before_creating_a_job(tmp_path: Path, client_and_manager, field: str) -> None:
    client, manager = client_and_manager

    response = client.post(
        "/api/jobs",
        data=FORM,
        files={field: ("marca.jpg", _image(tmp_path, "marca.jpg", "white"), "image/jpeg")},
    )

    assert response.status_code == 400
    assert "PNG sem fundo" in response.json()["detail"]
    manager.create_job.assert_not_called()


def test_transparent_brand_images_and_opaque_color_reference_are_accepted(tmp_path: Path, client_and_manager) -> None:
    client, manager = client_and_manager

    response = client.post(
        "/api/jobs",
        data=FORM,
        files={
            "ref_embalagem": ("embalagem.png", _image(tmp_path, "embalagem.png", "white@0.0"), "image/png"),
            "ref_logo": ("logo.png", _image(tmp_path, "logo.png", "white@0.0"), "image/png"),
            "ref_cores": ("cores.jpg", _image(tmp_path, "cores.jpg", "red"), "image/jpeg"),
        },
    )

    assert response.status_code == 200
    manager.create_job.assert_called_once()
