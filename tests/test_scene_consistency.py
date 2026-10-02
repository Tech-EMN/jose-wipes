import json
from unittest.mock import patch

from webapp.model_registry import get_model_config
from webapp.planner import (
    CAST_PROMPT_PREFIX,
    CONTINUOUS_TAKE_VISUAL_CONSTRAINT,
    _planner_system_prompt,
    plan_web_video,
)
from webapp.schemas import CreateJobRequest

JOAO = "Brazilian man, 40s, medium-brown skin, short black hair, trimmed beard, faded navy t-shirt"
LIDER = "Brazilian man, 60s, light-brown skin, grey hair, round glasses, beige cardigan"


def _shot(index: int, characters: object, *, product: bool = False) -> dict[str, object]:
    return {
        "shot_number": index,
        "visual_prompt_en": "A dim support group room with folding chairs and cold fluorescent light overhead.",
        "duration_seconds": 5,
        "narration_text_pt": "Fala.",
        "voice_persona": "narrador",
        "overlay_text": None,
        "product_overlay": {"ativo": product, "posicao": "centro", "tamanho_pct": 50, "inicio_seg": 0},
        "characters": characters,
        "notes": "ok",
    }


def _plan(shots: list[dict[str, object]], cast: list[dict[str, str]]):
    payload = {
        "title": "Grupo de apoio",
        "enhanced_brief_pt": "Paródia.",
        "global_style": "Cinematográfico.",
        "final_cta_pt": "José Wipes.",
        "notes": "ok",
        "cast": cast,
        "shots": shots,
    }
    request = CreateJobRequest(
        resolution="720p",
        orientation="vertical",
        duration_seconds=10,
        prompt="Grupo de apoio sem texto na tela.",
        video_model="kling_3_0",
    )
    with patch("webapp.planner.OPENAI_API_KEY", "test-key"), patch(
        "webapp.planner.OpenAI", return_value=object()
    ), patch("webapp.planner.create_text_response", return_value=json.dumps(payload)):
        return plan_web_video(request, "", get_model_config("kling_3_0"))


def test_every_shot_repeats_the_cast_description_and_forbids_cuts() -> None:
    cast = [{"character_id": "Joao", "description_en": JOAO}, {"character_id": "lider", "description_en": LIDER}]

    plan = _plan([_shot(1, ["joao", "lider"]), _shot(2, ["JOAO", "desconhecido"], product=True)], cast)

    first, second = plan.shots
    assert first.visual_prompt_en.startswith(CAST_PROMPT_PREFIX)
    assert JOAO in first.visual_prompt_en and LIDER in first.visual_prompt_en
    assert JOAO in second.visual_prompt_en and LIDER not in second.visual_prompt_en
    assert "desconhecido" not in second.visual_prompt_en
    assert all(shot.visual_prompt_en.count(CONTINUOUS_TAKE_VISUAL_CONSTRAINT) == 1 for shot in plan.shots)


def test_shots_without_cast_still_get_a_continuous_take() -> None:
    plan = _plan([_shot(1, "joao"), _shot(2, None)], [])

    assert all(shot.characters == [] for shot in plan.shots)
    assert all(not shot.visual_prompt_en.startswith(CAST_PROMPT_PREFIX) for shot in plan.shots)
    assert all(CONTINUOUS_TAKE_VISUAL_CONSTRAINT in shot.visual_prompt_en for shot in plan.shots)


def test_system_prompt_asks_for_a_fixed_brazilian_cast() -> None:
    prompt = _planner_system_prompt(orientation="vertical")

    assert "## ELENCO FIXO" in prompt
    assert "homens brasileiros" in prompt
    assert "tomada continua" in prompt
