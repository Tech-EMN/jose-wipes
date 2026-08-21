import json
import re
from pathlib import Path
from unittest.mock import patch

from scripts.compositor import (
    _limitar_duracao,
    adicionar_logo_overlay,
    normalizar_cena,
    overlay_produto,
)
from scripts.gerador_midia import combinar_video_audio
from scripts.product_reference import prompt_pede_referencia_produto
from webapp.model_registry import get_model_config
from webapp.pipeline_service import render_planned_video
from webapp.planner import (
    NO_TEXT_VISUAL_CONSTRAINT,
    NO_NARRATION_VISUAL_CONSTRAINT,
    PRODUCT_COMPOSITING_VISUAL_CONSTRAINT,
    plan_web_video,
)
from webapp.schemas import (
    CreateJobRequest,
    PlannerOutput,
    PlannerShot,
    ProductOverlayConfig,
)


def _request(prompt: str) -> CreateJobRequest:
    return CreateJobRequest(
        resolution="720p",
        orientation="vertical",
        duration_seconds=10,
        prompt=prompt,
        video_model="sora_2",
    )


def _planner_payload() -> dict[str, object]:
    return {
        "title": "Jose Wipes",
        "enhanced_brief_pt": "Duas cenas de produto em fundo branco.",
        "global_style": "Minimalista e premium.",
        "final_cta_pt": "Jose Wipes.",
        "notes": "Sem pessoas.",
        "shots": [
            {
                "shot_number": index,
                "visual_prompt_en": (
                    "A premium wet wipes package on a clean white studio background. "
                    "A slow dolly-in creates subtle camera movement. "
                    "Film grain and bokeh remain visible around the product."
                ),
                "duration_seconds": 5,
                "narration_text_pt": "Narracao indevida",
                "voice_persona": "narrador",
                "overlay_text": "Texto que nao deve aparecer",
                "product_overlay": {
                    "ativo": True,
                    "posicao": "centro",
                    "tamanho_pct": 55,
                    "inicio_seg": 2,
                },
                "notes": "Produto centralizado.",
            }
            for index in range(1, 3)
        ],
    }


def test_planner_honors_no_text_brief() -> None:
    request = _request(
        "Sem narracao. Não mostre pessoas, mãos ou texto na tela. Mostre a embalagem."
    )

    with patch("webapp.planner.OPENAI_API_KEY", "test-key"), patch(
        "webapp.planner.OpenAI", return_value=object()
    ), patch(
        "webapp.planner.create_text_response",
        return_value=json.dumps(_planner_payload()),
    ):
        plan = plan_web_video(request, "", get_model_config("sora_2"))

    assert all(shot.overlay_text is None for shot in plan.shots)
    assert all(shot.narration_text_pt == "" for shot in plan.shots)
    assert all(NO_TEXT_VISUAL_CONSTRAINT in shot.visual_prompt_en for shot in plan.shots)
    assert all(NO_NARRATION_VISUAL_CONSTRAINT in shot.visual_prompt_en for shot in plan.shots)
    assert all(
        PRODUCT_COMPOSITING_VISUAL_CONSTRAINT in shot.visual_prompt_en
        for shot in plan.shots
    )
    assert all(not prompt_pede_referencia_produto(shot.visual_prompt_en) for shot in plan.shots)
    assert all(re.search(r"\bproduct\b", shot.visual_prompt_en, re.IGNORECASE) is None for shot in plan.shots)
    assert all("locked-off camera" in shot.visual_prompt_en for shot in plan.shots)
    assert all("dolly" not in shot.visual_prompt_en.lower() for shot in plan.shots)
    assert all(shot.product_overlay.posicao == "centro_inferior" for shot in plan.shots)
    assert all(shot.product_overlay.tamanho_pct >= 70 for shot in plan.shots)
    assert all(shot.product_overlay.inicio_seg == 0 for shot in plan.shots)


def test_product_overlay_replaces_generation_reference(tmp_path: Path) -> None:
    product_path = tmp_path / "product.png"
    product_path.write_bytes(b"product")
    plan = PlannerOutput(
        title="Jose Wipes",
        enhanced_brief_pt="Produto em fundo branco.",
        global_style="Minimalista.",
        final_cta_pt="Jose Wipes.",
        shots=[
            PlannerShot(
                shot_number=1,
                visual_prompt_en="A premium wet wipes package on a clean white studio background.",
                product_overlay=ProductOverlayConfig(ativo=True),
            )
        ],
    )

    def generate(*_args: object, **kwargs: object) -> Path:
        output_path = Path(str(kwargs["output_path"]))
        output_path.write_bytes(b"video")
        return output_path

    def overlay(*_args: object, **kwargs: object) -> Path:
        output_path = Path(str(_args[1]))
        output_path.write_bytes(b"composited")
        return output_path

    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"final")

    with patch(
        "webapp.pipeline_service.obter_path_imagem_produto", return_value=product_path
    ), patch(
        "webapp.pipeline_service.obter_url_imagem_produto",
        return_value="https://example.com/product.png",
    ) as product_url_mock, patch(
        "webapp.pipeline_service._gerar_video_com_fallback", side_effect=generate
    ) as generate_mock, patch(
        "webapp.pipeline_service.overlay_produto", side_effect=overlay
    ) as product_overlay_mock, patch(
        "webapp.pipeline_service.gerar_card_logo", return_value=None
    ), patch(
        "webapp.pipeline_service.compor_video_final", return_value=final_path
    ), patch(
        "webapp.pipeline_service.upload_para_drive", return_value=None
    ):
        render_planned_video(
            job_dir=tmp_path / "job",
            request=_request("Mostre a embalagem."),
            plan=plan,
            model_config=get_model_config("sora_2"),
            apply_logo_overlay=False,
        )

    assert generate_mock.call_args.kwargs["reference_image_path"] is None
    assert generate_mock.call_args.kwargs["reference_image_url"] is None
    product_url_mock.assert_not_called()
    product_overlay_mock.assert_called_once()


def test_none_logo_path_copies_video_without_watermark(tmp_path: Path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"video")

    with patch("scripts.compositor._subprocess_run") as subprocess_mock:
        result = adicionar_logo_overlay(input_path, None, output_path)

    subprocess_mock.assert_not_called()
    assert result == output_path
    assert output_path.read_bytes() == b"video"


def test_product_overlay_adds_contact_shadow(tmp_path: Path) -> None:
    video_path = tmp_path / "video.mp4"
    product_path = tmp_path / "product.png"
    output_path = tmp_path / "output.mp4"
    video_path.write_bytes(b"video")
    product_path.write_bytes(b"product")

    with patch(
        "scripts.compositor._obter_dimensoes_video",
        return_value=(720, 1280),
    ), patch("scripts.compositor._subprocess_run") as subprocess_mock:
        result = overlay_produto(
            video_path,
            output_path,
            produto_path=product_path,
            posicao="centro_inferior",
            tamanho_pct=70,
        )

    filter_complex = subprocess_mock.call_args.args[0][
        subprocess_mock.call_args.args[0].index("-filter_complex") + 1
    ]
    assert "gblur=sigma=12" in filter_complex
    assert "colorchannelmixer=rr=0:gg=0:bb=0:aa=0.3" in filter_complex
    assert "loop=loop=-1:size=1:start=0" in filter_complex
    assert "shortest=1" in filter_complex
    assert "scale=504:-1" in filter_complex
    assert result == output_path


def test_exact_target_dimensions_skip_letterbox_detection(tmp_path: Path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"video")

    with patch(
        "scripts.compositor._obter_dimensoes_video",
        return_value=(720, 1280),
    ), patch(
        "scripts.compositor._detectar_crop_sem_letterbox"
    ) as crop_mock, patch("scripts.compositor._subprocess_run") as run_mock:
        result = normalizar_cena(input_path, output_path, largura=720, altura=1280)

    video_filter = run_mock.call_args.args[0][run_mock.call_args.args[0].index("-vf") + 1]
    crop_mock.assert_not_called()
    assert video_filter.startswith("scale=720:1280")
    assert result == output_path


def test_duration_limiter_fits_requested_duration(tmp_path: Path) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"long video")

    def create_trimmed(command: list[str], **_kwargs: object) -> None:
        Path(command[-1]).write_bytes(b"trimmed video")

    with patch("scripts.compositor._subprocess_run", side_effect=create_trimmed) as run_mock:
        result = _limitar_duracao(video_path, 10)

    command = run_mock.call_args.args[0]
    assert command[command.index("-t") + 1] == "10.000"
    assert "tpad=stop_mode=clone:stop_duration=10.000" in command[command.index("-vf") + 1]
    assert "apad=pad_dur=10.000" in command[command.index("-af") + 1]
    assert result == video_path
    assert video_path.read_bytes() == b"trimmed video"


def test_audio_shorter_than_video_keeps_video_duration(tmp_path: Path) -> None:
    output_path = tmp_path / "combined.mp4"

    with patch(
        "scripts.gerador_midia._probe_duration_seconds", side_effect=[4.0, 1.9]
    ), patch("scripts.gerador_midia._subprocess_run") as run_mock:
        result = combinar_video_audio("video.mp4", "audio.mp3", output_path)

    command = run_mock.call_args.args[0]
    assert "-shortest" not in command
    assert command[command.index("-t") + 1] == "4.000"
    assert "apad=pad_dur=4.000" in command[command.index("-af") + 1]
    assert result == output_path
