import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.compositor import compor_video_final
from scripts.gerador_midia import combinar_video_audio
from webapp.model_registry import get_model_config
from webapp.narration_plan import (
    DurationRange,
    NarrationClip,
    budget_warning,
    fit_narration_to_budget,
    shot_duration_for,
    split_sentences,
)
from webapp.pipeline_service import _faixa_de_duracao, render_planned_video
from webapp.schemas import CreateJobRequest, PlannerOutput, PlannerShot

KLING_RANGE = DurationRange(min_seconds=3, max_seconds=15)
SECONDS_PER_WORD = 0.5


def _fake_synthesizer(calls: list[tuple[int, str]]):
    def synthesize(shot_index: int, text: str) -> NarrationClip:
        calls.append((shot_index, text))
        return NarrationClip(
            text=text,
            audio_path=Path(f"shot_{shot_index}.mp3"),
            duration_seconds=len(text.split()) * SECONDS_PER_WORD,
        )

    return synthesize


def test_sentences_split_on_terminal_punctuation() -> None:
    assert split_sentences("Primeira frase. Segunda?  Terceira!") == ["Primeira frase.", "Segunda?", "Terceira!"]
    assert split_sentences("   ") == []


@pytest.mark.parametrize(
    ("audio_seconds", "planned", "expected"),
    [(4.2, 5, 5), (2.1, 5, 3), (14.8, 5, 15), (20.0, 5, 15), (None, 5, 5), (None, 1, 3)],
)
def test_shot_duration_follows_narration(audio_seconds, planned, expected) -> None:
    clip = None if audio_seconds is None else NarrationClip("texto", Path("a.mp3"), audio_seconds)

    assert shot_duration_for(clip, planned, KLING_RANGE) == expected


def test_narration_that_fits_keeps_every_sentence() -> None:
    calls: list[tuple[int, str]] = []

    budget = fit_narration_to_budget(
        ["Eu usei só papel.", "José uáipes resolve."],
        [5, 5],
        budget_seconds=7,
        duration_range=KLING_RANGE,
        synthesize=_fake_synthesizer(calls),
    )

    assert budget.removed_sentences == ()
    assert budget.shot_durations == (3, 3)
    assert calls == [(0, "Eu usei só papel."), (1, "José uáipes resolve.")]


def test_overflow_drops_whole_sentences_before_the_final_line() -> None:
    calls: list[tuple[int, str]] = []
    narrations = [
        "Primeira fala do grupo. Segunda fala bem mais longa do grupo inteiro.",
        "Terceira fala que também é longa demais para caber. Quarta fala.",
        "José uáipes. Limpeza de verdade.",
    ]

    budget = fit_narration_to_budget(
        narrations,
        [5, 5, 5],
        budget_seconds=13,
        duration_range=KLING_RANGE,
        synthesize=_fake_synthesizer(calls),
    )

    assert budget.removed_sentences == ("Terceira fala que também é longa demais para caber.", "Quarta fala.")
    assert budget.clips[0].text == narrations[0]
    assert budget.clips[1] is None
    assert budget.clips[2].text == "José uáipes. Limpeza de verdade."
    assert budget.shot_durations == (7, 3, 3)
    assert budget.required_seconds == 16
    assert calls[-1] == (1, "Terceira fala que também é longa demais para caber.")


def test_when_nothing_else_fits_silent_shots_shrink_to_the_minimum() -> None:
    budget = fit_narration_to_budget(
        ["Uma fala com muitas palavras que nunca vai caber no teto pedido.", ""],
        [10, 10],
        budget_seconds=6,
        duration_range=KLING_RANGE,
        synthesize=_fake_synthesizer([]),
    )

    assert budget.clips == (None, None)
    assert budget.shot_durations == (3, 3)


def test_budget_warning_lists_removed_sentences_and_suggests_next_duration() -> None:
    budget = fit_narration_to_budget(
        ["Uma frase curta. Outra frase que não cabe de jeito nenhum aqui.", "José uáipes."],
        [5, 5],
        budget_seconds=7,
        duration_range=KLING_RANGE,
        synthesize=_fake_synthesizer([]),
    )

    warning = budget_warning(budget, ceiling_seconds=10, reserved_seconds=3, available_ceilings=(10, 30, 60))

    assert warning is not None
    assert "não coube em 10s" in warning
    assert "«Outra frase que não cabe de jeito nenhum aqui.»" in warning
    assert "Use a duração de 30s" in warning


def test_budget_warning_is_absent_when_everything_fits() -> None:
    budget = fit_narration_to_budget(
        ["Curta."], [5], budget_seconds=7, duration_range=KLING_RANGE, synthesize=_fake_synthesizer([])
    )

    assert budget_warning(budget, ceiling_seconds=10, reserved_seconds=3, available_ceilings=(10, 30, 60)) is None


def test_duration_range_is_the_intersection_of_primary_and_fallback_models() -> None:
    professional = _faixa_de_duracao(get_model_config("veo_3_1"))
    realistic = _faixa_de_duracao(get_model_config("kling_3_0"))

    assert professional == DurationRange(min_seconds=3, max_seconds=15)
    assert realistic == DurationRange(min_seconds=3, max_seconds=15)


def test_long_narration_is_never_truncated_when_combined() -> None:
    with patch("scripts.gerador_midia._probe_duration_seconds", side_effect=[4.0, 7.5]), patch(
        "scripts.gerador_midia._subprocess_run"
    ) as run_mock:
        combinar_video_audio("video.mp4", "audio.mp3", "out.mp4")

    command = run_mock.call_args.args[0]
    assert command[command.index("-t") + 1] == "7.700"


def _probe(duration: float) -> object:
    payload = json.dumps(
        {
            "format": {"duration": str(duration), "size": "1024"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 720, "height": 1280},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
    )
    return type("Probe", (), {"stdout": payload})()


def _compose(tmp_path: Path, probed_duration: float):
    final_path = tmp_path / "final" / "result.mp4"
    with patch(
        "scripts.compositor.normalizar_cena",
        side_effect=[tmp_path / "scene.mp4", tmp_path / "card.mp4"],
    ), patch(
        "scripts.compositor.concatenar_cenas",
        side_effect=lambda _scenes, output: Path(output),
    ), patch(
        "scripts.compositor._limitar_duracao",
        side_effect=lambda path, _duration: Path(path),
    ) as limiter_mock, patch(
        "scripts.compositor.adicionar_logo_overlay",
        return_value=final_path,
    ), patch(
        "scripts.compositor._subprocess_run",
        return_value=_probe(probed_duration),
    ):
        result = compor_video_final(
            [tmp_path / "scene.mp4", tmp_path / "card.mp4"],
            "Jose Wipes",
            largura=720,
            altura=1280,
            output_dir=tmp_path / "final",
            duracao_maxima=10,
            duracao_card_final=3,
        )
    return result, limiter_mock


def test_video_shorter_than_ceiling_is_accepted_without_trimming(tmp_path: Path) -> None:
    result, limiter_mock = _compose(tmp_path, 6.5)

    assert result is not None
    limiter_mock.assert_not_called()


def test_video_longer_than_ceiling_is_rejected(tmp_path: Path) -> None:
    result, limiter_mock = _compose(tmp_path, 10.6)

    assert result is None
    limiter_mock.assert_called_once()


def test_render_generates_narration_before_video_and_sizes_shots_from_it(tmp_path: Path) -> None:
    plan = PlannerOutput(
        title="Jose Wipes",
        enhanced_brief_pt="Grupo de apoio.",
        global_style="Cinematográfico.",
        final_cta_pt="José Wipes.",
        shots=[
            PlannerShot(
                shot_number=index,
                visual_prompt_en="A dim support group room with men sitting in a circle.",
                narration_text_pt=text,
                duration_seconds=5,
            )
            for index, text in enumerate(("Eu usei só papel, gente.", "José uáipes resolve."), start=1)
        ],
    )
    events: list[str] = []
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"final")

    def fake_audio(_persona: str, text: str, output_path: str) -> str:
        events.append(f"audio:{text}")
        return output_path

    def fake_video(*_args, **kwargs) -> Path:
        events.append(f"video:{kwargs['duracao']}")
        return tmp_path / "generated.mp4"

    with patch("webapp.pipeline_service.gerar_audio_elevenlabs", side_effect=fake_audio), patch(
        "webapp.pipeline_service.medir_duracao_segundos", side_effect=[3.1, 2.2]
    ), patch("webapp.pipeline_service._gerar_video_com_fallback", side_effect=fake_video), patch(
        "webapp.pipeline_service.combinar_video_audio", side_effect=lambda _v, _a, out: out
    ), patch("webapp.pipeline_service.obter_path_imagem_produto", return_value=None), patch(
        "webapp.pipeline_service.compor_video_final", return_value=final_path
    ), patch("webapp.pipeline_service.upload_para_drive", return_value={"id": "1", "link": "l"}):
        result = render_planned_video(
            job_dir=tmp_path / "job",
            request=CreateJobRequest(
                resolution="720p",
                orientation="vertical",
                duration_seconds=10,
                prompt="Grupo de apoio.",
                video_model="kling_3_0",
            ),
            plan=plan,
            model_config=get_model_config("kling_3_0"),
            apply_logo_overlay=False,
        )

    assert events == [
        "audio:Eu usei só papel, gente.",
        "audio:José uáipes resolve.",
        "video:4",
        "video:3",
    ]
    assert result["warnings"] == []


def test_silent_shots_shrink_before_any_sentence_is_dropped() -> None:
    budget = fit_narration_to_budget(
        ["Fala de quatro palavras.", "", "Mais quatro palavras aqui."],
        [5, 5, 5],
        budget_seconds=9,
        duration_range=KLING_RANGE,
        synthesize=_fake_synthesizer([]),
    )

    assert budget.removed_sentences == ()
    assert budget.shot_durations == (3, 3, 3)


def test_mismatched_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        fit_narration_to_budget(
            ["Uma."], [5, 5], budget_seconds=10, duration_range=KLING_RANGE, synthesize=_fake_synthesizer([])
        )
