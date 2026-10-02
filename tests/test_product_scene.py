from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import webapp.model_registry as registry
from scripts.higgsfield_model_profiles import (
    KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION,
    KLING_3_0_STD_IMAGE_TO_VIDEO_APPLICATION,
    SOUL_2_APPLICATION,
    WAN_3_0_PRIME_IMAGE_TO_VIDEO_APPLICATION,
    find_argument_profile,
)
from scripts.integration_errors import IntegrationFailure
from webapp.model_registry import VideoModelConfig, get_model_config
from webapp.pipeline_service import render_planned_video
from webapp.planner import PRODUCT_COMPOSITING_VISUAL_CONSTRAINT
from webapp.product_scene import (
    ANIMATION_CONSTRAINT,
    KEYFRAME_SURFACE_HINT,
    KeyframeSpec,
    animation_prompt,
    keyframe_prompt,
    render_product_keyframe,
    shot_integrates_product,
)
from webapp.schemas import CreateJobRequest, PlannerOutput, PlannerShot, ProductOverlayConfig

COMPOSED_PROMPT = (
    "A dim support group room with a wooden table in the foreground. "
    "Keep a clean empty lower central placement area on the primary surface. "
    f"{PRODUCT_COMPOSITING_VISUAL_CONSTRAINT}"
)
KEYFRAME_URL = "https://cdn.example.com/keyframe.png"


def _shot(number: int, *, active: bool, start: float | None = 0.0) -> PlannerShot:
    return PlannerShot(
        shot_number=number,
        visual_prompt_en=COMPOSED_PROMPT,
        narration_text_pt="José uáipes resolve.",
        product_overlay=ProductOverlayConfig(ativo=active, posicao="centro_inferior", tamanho_pct=50, inicio_seg=start),
    )


def test_animation_prompt_drops_the_empty_area_and_keeps_the_package_still() -> None:
    prompt = animation_prompt(COMPOSED_PROMPT)

    assert "placement area" not in prompt
    assert PRODUCT_COMPOSITING_VISUAL_CONSTRAINT not in prompt
    assert prompt.startswith("A dim support group room with a wooden table in the foreground.")
    assert prompt.endswith(ANIMATION_CONSTRAINT)


def test_keyframe_prompt_asks_for_a_surface() -> None:
    assert keyframe_prompt(COMPOSED_PROMPT).endswith(KEYFRAME_SURFACE_HINT)


@pytest.mark.parametrize(
    ("active", "start", "expected"),
    [(True, 0.0, True), (True, None, True), (True, 2.0, False), (False, 0.0, False)],
)
def test_only_still_product_shots_are_integrated(active: bool, start: float | None, expected: bool) -> None:
    assert shot_integrates_product(_shot(1, active=active, start=start)) is expected


@pytest.mark.parametrize(
    ("key", "resolution", "application", "fallback"),
    [
        ("seedance_1_5_pro", "720p", KLING_3_0_STD_IMAGE_TO_VIDEO_APPLICATION, KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION),
        ("seedance_1_5_pro", "1080p", KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION, ""),
        ("kling_3_0", "1080p", KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION, ""),
        ("veo_3_1", "1080p", WAN_3_0_PRIME_IMAGE_TO_VIDEO_APPLICATION, KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION),
    ],
)
def test_every_tier_has_an_image_to_video_counterpart(key: str, resolution: str, application: str, fallback: str) -> None:
    image_model = get_model_config(key).for_resolution(resolution).image_to_video()

    assert image_model is not None
    assert image_model.application == application
    assert image_model.fallback_application == fallback
    assert find_argument_profile(application).uses_image


def test_unknown_model_has_no_image_to_video_counterpart() -> None:
    config = VideoModelConfig(
        key="kling_3_0", label="x", tier="x", application="vendor/other/text-to-video", allowed_resolutions=("720p",)
    )

    assert config.image_to_video() is None


def test_wan_image_to_video_sends_the_keyframe_as_first_frame() -> None:
    arguments = find_argument_profile(WAN_3_0_PRIME_IMAGE_TO_VIDEO_APPLICATION).build_arguments(
        prompt="p", aspect_ratio="9:16", resolution="1080p", duration_seconds=6, reference_image_url=KEYFRAME_URL
    )

    assert arguments == {
        "prompt": "p",
        "duration": 6,
        "generate_audio": False,
        "aspect_ratio": "9:16",
        "resolution": "1080p",
        "image_url": KEYFRAME_URL,
    }


def _spec(tmp_path: Path) -> KeyframeSpec:
    return KeyframeSpec(
        prompt=COMPOSED_PROMPT,
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        product_path=tmp_path / "produto.png",
        position="centro_inferior",
        size_pct=50,
        output_dir=tmp_path,
        name="shot_01",
    )


def test_keyframe_is_generated_with_soul_and_receives_the_package(tmp_path: Path) -> None:
    still = tmp_path / "shot_01_cena.png"
    composed = tmp_path / "shot_01_cena_produto.png"
    with patch("webapp.product_scene.gerar_video_higgsfield", return_value=str(still)) as generate, patch(
        "webapp.product_scene.compor_produto_em_cena", return_value=composed
    ) as compose:
        result = render_product_keyframe(_spec(tmp_path))

    assert result == composed
    assert generate.call_args.args[0] == SOUL_2_APPLICATION
    assert generate.call_args.kwargs["aspecto"] == "9:16"
    assert compose.call_args.kwargs["largura"] == 1080


def test_keyframe_composition_failure_is_reported(tmp_path: Path) -> None:
    with patch("webapp.product_scene.gerar_video_higgsfield", return_value=str(tmp_path / "s.png")), patch(
        "webapp.product_scene.compor_produto_em_cena", return_value=None
    ), pytest.raises(IntegrationFailure) as captured:
        render_product_keyframe(_spec(tmp_path))

    assert captured.value.code == "keyframe_composition_failed"


def _render(tmp_path: Path, shots: list[PlannerShot], *, keyframe_effect: object):
    plan = PlannerOutput(
        title="Grupo", enhanced_brief_pt="b", global_style="Cinematográfico.", final_cta_pt="José Wipes.", shots=shots
    )
    generated: list[tuple[str, str, str | None]] = []
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"final")

    def fake_video(model_config: VideoModelConfig, prompt: str, **kwargs: object) -> Path:
        generated.append((model_config.application, prompt, kwargs["reference_image_url"]))
        return tmp_path / f"generated_{len(generated)}.mp4"

    overlay = MagicMock(side_effect=lambda video, output, **_kwargs: output)
    keyframe = MagicMock(side_effect=keyframe_effect)
    with patch("webapp.pipeline_service.gerar_audio_elevenlabs", side_effect=lambda _p, _t, out: out), patch(
        "webapp.pipeline_service.medir_duracao_segundos", return_value=2.0
    ), patch("webapp.pipeline_service._gerar_video_com_fallback", side_effect=fake_video), patch(
        "webapp.pipeline_service.render_product_keyframe", keyframe
    ), patch("webapp.pipeline_service._upload_reference_image", return_value=KEYFRAME_URL), patch(
        "webapp.pipeline_service.combinar_video_audio", side_effect=lambda _v, _a, out: out
    ), patch("webapp.pipeline_service.overlay_produto", overlay), patch(
        "webapp.pipeline_service.adicionar_texto_overlay", side_effect=lambda video, _t, out, _p: out
    ), patch("webapp.pipeline_service.gerar_card_logo", side_effect=lambda out, *_a, **_k: out), patch(
        "webapp.pipeline_service.compor_video_final", return_value=final_path
    ), patch("webapp.pipeline_service.upload_para_drive", return_value={"id": "1", "link": "l"}):
        result = render_planned_video(
            job_dir=tmp_path / "job",
            request=CreateJobRequest(
                resolution="1080p", orientation="vertical", duration_seconds=30, prompt="Grupo.", video_model="kling_3_0"
            ),
            plan=plan,
            model_config=get_model_config("kling_3_0"),
            apply_logo_overlay=False,
        )
    return generated, overlay, keyframe, result


def test_still_product_shot_is_animated_from_a_keyframe_with_the_package(tmp_path: Path) -> None:
    composed = tmp_path / "keyframe.png"
    generated, overlay, keyframe, result = _render(
        tmp_path, [_shot(1, active=False), _shot(2, active=True)], keyframe_effect=lambda _spec: composed
    )

    assert generated[0][0] == registry.KLING_3_0_PRO_APPLICATION
    assert generated[1] == (KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION, animation_prompt(COMPOSED_PROMPT), KEYFRAME_URL)
    assert keyframe.call_args.args[0].width == 1080
    overlay.assert_not_called()
    assert not any("embalagem dentro da cena" in warning for warning in result["warnings"])


def test_failed_keyframe_falls_back_to_the_overlay_with_a_warning(tmp_path: Path) -> None:
    failure = IntegrationFailure(service="higgsfield", stage="generating_keyframe", code="keyframe_failed", user_message="x")

    generated, overlay, _keyframe, result = _render(tmp_path, [_shot(1, active=True)], keyframe_effect=failure)

    assert generated == [(registry.KLING_3_0_PRO_APPLICATION, COMPOSED_PROMPT, None)]
    overlay.assert_called_once()
    assert any("keyframe_failed" in warning for warning in result["warnings"])


def test_gesture_shot_keeps_the_overlay(tmp_path: Path) -> None:
    generated, overlay, keyframe, _result = _render(tmp_path, [_shot(1, active=True, start=2.0)], keyframe_effect=None)

    keyframe.assert_not_called()
    assert generated[0][2] is None
    overlay.assert_called_once()


def test_planner_prefers_the_package_resting_on_a_surface() -> None:
    from webapp.planner import _planner_system_prompt

    prompt = _planner_system_prompt(orientation="vertical")

    assert "prefira o produto apoiado numa superficie" in prompt
    assert "Use gesto de erguer o produto so quando o roteiro exigir" in prompt
