import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from jose_wipes.integrations.errors import IntegrationFailure
from jose_wipes.model_registry import get_model_config
from jose_wipes.rendering.pipeline_service import (
    RENDER_STAGES_FILENAME,
    ComposedVideo,
    RenderInputs,
    compose_video,
    generate_media,
    plan_render,
    publish_video,
    render_planned_video,
)
from jose_wipes.result import Err, Ok
from jose_wipes.schemas import CreateJobRequest, PlannerOutput, PlannerShot

MODULE = "jose_wipes.rendering.pipeline_service"
DRIVE_WARNING = "Google Drive indisponível; o vídeo permanece disponível para download pelo Studio."


def _request(resolution: str = "720p") -> CreateJobRequest:
    return CreateJobRequest(
        resolution=resolution,
        orientation="vertical",
        duration_seconds=10,
        prompt="Crie uma cena institucional sem narração.",
        video_model="kling_3_0",
    )


def _plan(narration: str = "") -> PlannerOutput:
    return PlannerOutput(
        title="Jose Wipes",
        enhanced_brief_pt="Cena institucional.",
        global_style="Minimalista.",
        final_cta_pt="Jose Wipes.",
        shots=[
            PlannerShot(
                shot_number=1,
                visual_prompt_en="A clean monochrome studio scene with subtle camera movement.",
                narration_text_pt=narration,
            )
        ],
    )


def _inputs(tmp_path: Path, *, narration: str = "", resolution: str = "720p") -> RenderInputs:
    return RenderInputs(
        job_dir=tmp_path / "job",
        request=_request(resolution),
        plan=_plan(narration),
        model_config=get_model_config("kling_3_0"),
        apply_logo_overlay=False,
    )


def _video(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"video")
    return path


def _planned(tmp_path: Path, **kwargs: str):
    with patch(f"{MODULE}.obter_path_imagem_produto", return_value=None):
        result = plan_render(_inputs(tmp_path, **kwargs))
    assert isinstance(result, Ok)
    return result.value


def test_plan_returns_error_for_unsupported_resolution(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    inputs = replace(inputs, model_config=replace(inputs.model_config, allowed_resolutions=("1080p",)))

    result = plan_render(inputs)

    assert isinstance(result, Err)
    assert result.failure.code == "resolution_not_supported"
    assert result.failure.retryable is False


def test_generate_media_returns_error_when_narration_fails(tmp_path: Path) -> None:
    render_plan = _planned(tmp_path, narration="Uma frase de narração.")

    with patch(f"{MODULE}.gerar_audio_elevenlabs", return_value=None), patch(
        f"{MODULE}._gerar_video_com_fallback"
    ) as generate_video:
        result = generate_media(render_plan)

    assert isinstance(result, Err)
    assert result.failure.code == "narration_failed"
    generate_video.assert_not_called()


def test_generate_media_returns_error_when_the_scene_has_no_output(tmp_path: Path) -> None:
    render_plan = _planned(tmp_path)

    with patch(f"{MODULE}._gerar_video_com_fallback", return_value=None):
        result = generate_media(render_plan)

    assert isinstance(result, Err)
    assert result.failure.code == "scene_generation_failed"


def test_compose_runs_from_generated_media_without_regenerating(tmp_path: Path) -> None:
    render_plan = _planned(tmp_path)
    with patch(f"{MODULE}._gerar_video_com_fallback", return_value=_video(tmp_path, "raw.mp4")):
        media = generate_media(render_plan)
    assert isinstance(media, Ok)

    final_path = _video(tmp_path, "final.mp4")
    with patch(f"{MODULE}._gerar_video_com_fallback") as generate_video, patch(
        f"{MODULE}.compor_video_final", return_value=final_path
    ):
        first = compose_video(render_plan, media.value)
        second = compose_video(render_plan, media.value)

    generate_video.assert_not_called()
    assert isinstance(first, Ok) and isinstance(second, Ok)
    assert second.value.final_video_path == final_path


def test_compose_returns_error_when_final_video_is_invalid(tmp_path: Path) -> None:
    render_plan = _planned(tmp_path)
    with patch(f"{MODULE}._gerar_video_com_fallback", return_value=_video(tmp_path, "raw.mp4")):
        media = generate_media(render_plan)
    assert isinstance(media, Ok)

    with patch(f"{MODULE}.compor_video_final", return_value=None):
        result = compose_video(render_plan, media.value)

    assert isinstance(result, Err)
    assert result.failure.code == "final_video_invalid"


@pytest.mark.parametrize(
    ("drive_required", "expected_type"),
    [(False, Ok), (True, Err)],
)
def test_publish_follows_drive_policy(tmp_path: Path, drive_required: bool, expected_type: type) -> None:
    composed = ComposedVideo(final_video_path=_video(tmp_path, "final.mp4"), scene_paths=(), warnings=())

    with patch(f"{MODULE}.upload_para_drive", return_value=None), patch(
        f"{MODULE}.JW_DRIVE_REQUIRED", drive_required
    ):
        result = publish_video(composed)

    assert isinstance(result, expected_type)
    if isinstance(result, Ok):
        assert result.value.warnings == (DRIVE_WARNING,)
    else:
        assert result.failure.code == "drive_upload_failed"
        assert result.failure.render_confirmed is True


def _stages(job_dir: Path) -> dict[str, dict[str, object]]:
    return json.loads((job_dir / RENDER_STAGES_FILENAME).read_text(encoding="utf-8"))


def _stage_statuses(job_dir: Path) -> dict[str, object]:
    return {name: entry["status"] for name, entry in _stages(job_dir).items()}


def _render(tmp_path: Path, *, drive_required: bool) -> dict[str, object]:
    inputs = _inputs(tmp_path)
    with patch(f"{MODULE}._gerar_video_com_fallback", return_value=_video(tmp_path, "raw.mp4")), patch(
        f"{MODULE}.obter_path_imagem_produto", return_value=None
    ), patch(f"{MODULE}.compor_video_final", return_value=_video(tmp_path, "final.mp4")), patch(
        f"{MODULE}.upload_para_drive", return_value=None
    ), patch(f"{MODULE}.JW_DRIVE_REQUIRED", drive_required):
        return render_planned_video(
            job_dir=inputs.job_dir,
            request=inputs.request,
            plan=inputs.plan,
            model_config=inputs.model_config,
            apply_logo_overlay=False,
        )


def test_render_records_every_completed_stage(tmp_path: Path) -> None:
    result = _render(tmp_path, drive_required=False)

    assert result["warnings"] == [DRIVE_WARNING]
    assert _stage_statuses(tmp_path / "job") == {
        "plan": "completed",
        "generate_media": "completed",
        "compose": "completed",
        "publish": "completed",
    }


def test_render_records_the_stage_that_failed(tmp_path: Path) -> None:
    with pytest.raises(IntegrationFailure) as captured:
        _render(tmp_path, drive_required=True)

    assert captured.value.code == "drive_upload_failed"
    stages = _stages(tmp_path / "job")
    assert _stage_statuses(tmp_path / "job") == {
        "plan": "completed",
        "generate_media": "completed",
        "compose": "completed",
        "publish": "failed",
    }
    assert stages["publish"]["failure_code"] == "drive_upload_failed"
    assert stages["publish"]["retryable"] is True

