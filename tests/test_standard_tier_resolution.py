from pathlib import Path
from unittest.mock import patch

from scripts.higgsfield_model_profiles import KLING_3_0_PRO_APPLICATION, KLING_3_0_STD_APPLICATION
from webapp.model_registry import VideoModelConfig, get_model_config
from webapp.pipeline_service import render_planned_video
from webapp.schemas import CreateJobRequest, PlannerOutput, PlannerShot


def _render(tmp_path: Path, resolution: str) -> tuple[list[VideoModelConfig], dict[str, object]]:
    plan = PlannerOutput(
        title="Jose Wipes",
        enhanced_brief_pt="Aeroporto.",
        global_style="Cinematográfico.",
        final_cta_pt="José Wipes.",
        shots=[
            PlannerShot(
                shot_number=1,
                visual_prompt_en="A busy airport hallway with a confident man walking under cold light.",
                narration_text_pt="José uáipes resolve.",
                duration_seconds=5,
            )
        ],
    )
    used_models: list[VideoModelConfig] = []
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"final")

    def fake_video(model_config: VideoModelConfig, *_args: object, **_kwargs: object) -> Path:
        used_models.append(model_config)
        return tmp_path / "generated.mp4"

    with patch(
        "webapp.pipeline_service.gerar_audio_elevenlabs", side_effect=lambda _p, _t, out: out
    ), patch("webapp.pipeline_service.medir_duracao_segundos", return_value=2.0), patch(
        "webapp.pipeline_service._gerar_video_com_fallback", side_effect=fake_video
    ), patch(
        "webapp.pipeline_service.combinar_video_audio", side_effect=lambda _v, _a, out: out
    ), patch("webapp.pipeline_service.obter_path_imagem_produto", return_value=None), patch(
        "webapp.pipeline_service.compor_video_final", return_value=final_path
    ), patch("webapp.pipeline_service.upload_para_drive", return_value={"id": "1", "link": "l"}):
        result = render_planned_video(
            job_dir=tmp_path / "job",
            request=CreateJobRequest(
                resolution=resolution,
                orientation="vertical",
                duration_seconds=10,
                prompt="Aeroporto.",
                video_model="seedance_1_5_pro",
            ),
            plan=plan,
            model_config=get_model_config("seedance_1_5_pro"),
            apply_logo_overlay=False,
        )
    return used_models, result


def test_standard_tier_renders_1080p_with_kling_pro_and_says_so(tmp_path: Path) -> None:
    used_models, result = _render(tmp_path, "1080p")

    assert [model.application for model in used_models] == [KLING_3_0_PRO_APPLICATION]
    assert used_models[0].fallback_application == ""
    assert any(KLING_3_0_PRO_APPLICATION in warning for warning in result["warnings"])


def test_standard_tier_keeps_kling_std_at_720p(tmp_path: Path) -> None:
    used_models, result = _render(tmp_path, "720p")

    assert [model.application for model in used_models] == [KLING_3_0_STD_APPLICATION]
    assert result["warnings"] == []
