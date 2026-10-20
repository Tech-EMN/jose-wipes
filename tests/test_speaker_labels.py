import json
from unittest.mock import patch

import pytest

from webapp.model_registry import get_model_config
from webapp.narration_plan import strip_speaker_labels
from webapp.planner import plan_web_video
from webapp.schemas import CreateJobRequest


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("JOÃO: Meu nome é João... e eu usei só papel.", "Meu nome é João... e eu usei só papel."),
        ("LÍDER: João, olhe para mim. A culpa não é sua.", "João, olhe para mim. A culpa não é sua."),
        ("Banheiro de estrada. CARLOS: Sem pedir licença.", "Banheiro de estrada. Sem pedir licença."),
        ("NARRADOR OFF: José Wipes.", "José Wipes."),
        ("Mas eu digo a vocês: existe um caminho.", "Mas eu digo a vocês: existe um caminho."),
        ("João: eu também.", "João: eu também."),
        ("José Wipes. A recuperação que você merece.", "José Wipes. A recuperação que você merece."),
    ],
)
def test_speaker_labels_are_not_read_aloud(text: str, expected: str) -> None:
    assert strip_speaker_labels(text) == expected


def test_planner_removes_speaker_labels_from_narration() -> None:
    payload = {
        "title": "Grupo de apoio",
        "enhanced_brief_pt": "Paródia.",
        "global_style": "Cinematográfico.",
        "final_cta_pt": "José Wipes.",
        "shots": [
            {
                "shot_number": index,
                "visual_prompt_en": "A dim support group room with folding chairs and cold fluorescent light overhead.",
                "narration_text_pt": narration,
                "voice_persona": "joao",
            }
            for index, narration in enumerate(["JOÃO: Meu nome é João.", "PEDRO: Virou confete."], start=1)
        ],
    }
    request = CreateJobRequest(
        resolution="720p", orientation="vertical", duration_seconds=10, prompt="Grupo de apoio.", video_model="kling_3_0"
    )
    with patch("webapp.planner.OPENAI_API_KEY", "test-key"), patch(
        "webapp.planner.OpenAI", return_value=object()
    ), patch("webapp.planner.create_text_response", return_value=json.dumps(payload)):
        plan = plan_web_video(request, "", get_model_config("kling_3_0"))

    assert [shot.narration_text_pt for shot in plan.shots] == ["Meu nome é João.", "Virou confete."]
