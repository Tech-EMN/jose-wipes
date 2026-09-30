import json
from pathlib import Path

from scripts.higgsfield_model_profiles import (
    KLING_3_0_PRO_APPLICATION,
    KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION,
    find_argument_profile,
)
from scripts.system_prompt import BLOCO_GUARDRAILS, BLOCO_MODELOS

PROJECT_ROOT = Path(__file__).parent.parent
DISCONTINUED_KLING_PREFIX = "kling-video/v2.1/"


def test_cli_planner_prompt_only_recommends_current_kling_models() -> None:
    prompt = BLOCO_MODELOS + BLOCO_GUARDRAILS

    assert DISCONTINUED_KLING_PREFIX not in prompt
    assert KLING_3_0_PRO_APPLICATION in prompt
    assert KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION in prompt


def test_cli_sources_do_not_reference_kling_2_1() -> None:
    for relative_path in (
        "scripts/pipeline.py",
        "scripts/system_prompt.py",
        "scripts/higgsfield_video_smoke_test.py",
    ):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert DISCONTINUED_KLING_PREFIX not in source, relative_path


def test_e2e_fixture_scenes_use_profiled_models() -> None:
    plan = json.loads((PROJECT_ROOT / "tests/fixtures/e2e_plan.json").read_text(encoding="utf-8"))

    for scene in plan["cenas"]:
        assert find_argument_profile(scene["modelo"]) is not None, scene["modelo"]
