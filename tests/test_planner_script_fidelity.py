import json
from unittest.mock import patch

import pytest

from webapp.model_registry import get_model_config
from webapp.planner import (
    _expected_shot_count,
    _narration_word_budget,
    _planner_system_prompt,
    plan_web_video,
)
from webapp.schemas import CreateJobRequest

SCRIPT_LINES = (
    "Aeroporto lotado, banheiro sem papel e um voo em quarenta minutos.",
    "Todo mundo já passou por isso e fingiu que estava tudo bem.",
    "José uáipes. Limpeza de verdade, em qualquer lugar.",
)


def _request(duration_seconds: int) -> CreateJobRequest:
    return CreateJobRequest(
        resolution="720p",
        orientation="vertical",
        duration_seconds=duration_seconds,
        prompt="Anuncio de aeroporto seguindo o roteiro do cliente.",
        video_model="kling_3_0",
    )


def _payload(narrations: list[str]) -> dict[str, object]:
    return {
        "title": "Aeroporto",
        "enhanced_brief_pt": "Roteiro do cliente.",
        "global_style": "Comercial premium.",
        "final_cta_pt": "Limpeza de verdade.",
        "notes": "ok",
        "shots": [
            {
                "shot_number": index,
                "visual_prompt_en": "A busy airport hallway with a confident man walking under cold fluorescent light.",
                "duration_seconds": 5,
                "narration_text_pt": narration,
                "voice_persona": "narrador",
                "overlay_text": None,
                "product_overlay": {"ativo": False, "posicao": "centro", "tamanho_pct": 50, "inicio_seg": 0},
                "notes": "ok",
            }
            for index, narration in enumerate(narrations, start=1)
        ],
    }


def _plan(duration_seconds: int, narrations: list[str], pdf_text: str) -> tuple[object, dict[str, object]]:
    captured: dict[str, object] = {}

    def respond(**kwargs: object) -> str:
        captured.update(kwargs)
        return json.dumps(_payload(narrations), ensure_ascii=False)

    with patch("webapp.planner.OPENAI_API_KEY", "test-key"), patch(
        "webapp.planner.OpenAI", return_value=object()
    ), patch("webapp.planner.create_text_response", side_effect=respond):
        plan = plan_web_video(_request(duration_seconds), pdf_text, get_model_config("kling_3_0"))
    return plan, captured


@pytest.mark.parametrize(("duration", "shots"), [(10, 2), (30, 5), (60, 11)])
def test_shot_count_leaves_room_for_the_brand_card(duration: int, shots: int) -> None:
    assert _expected_shot_count(duration) == shots


@pytest.mark.parametrize(("duration", "words"), [(10, 10), (30, 44), (60, 92)])
def test_word_budget_matches_the_content_time(duration: int, words: int) -> None:
    assert _narration_word_budget(duration) == words


def test_long_script_lines_reach_the_pipeline_untouched() -> None:
    narrations = [" ".join(SCRIPT_LINES[:2]), SCRIPT_LINES[2]]

    plan, _ = _plan(10, narrations, "\n".join(SCRIPT_LINES))

    assert [shot.narration_text_pt for shot in plan.shots] == narrations


def test_planner_receives_the_script_as_the_official_text() -> None:
    _, captured = _plan(30, list(SCRIPT_LINES) + ["", ""], "\n".join(SCRIPT_LINES))
    payload = json.loads(str(captured["user_input"]))

    assert payload["roteiro_cliente"] == "\n".join(SCRIPT_LINES)
    assert payload["shots_necessarios"] == 5
    assert payload["palavras_de_narracao_que_cabem"] == 44


def test_system_prompt_requires_literal_script_and_drops_fixed_shot_length() -> None:
    prompt = _planner_system_prompt(orientation="vertical")

    assert "## ROTEIRO DO CLIENTE" in prompt
    assert "exatamente como estao escritas" in prompt
    assert "sem seguir literalmente" not in prompt
    assert "5 segundos exatos" not in prompt
    assert "Limite duro" not in prompt
