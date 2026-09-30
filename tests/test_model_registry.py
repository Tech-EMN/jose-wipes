import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import webapp.model_registry as registry
from scripts.higgsfield_model_profiles import (
    KLING_3_0_PRO_APPLICATION,
    KLING_3_0_STD_APPLICATION,
    WAN_3_0_PRIME_APPLICATION,
    find_argument_profile,
)
from scripts.integration_errors import IntegrationFailure
from webapp.pipeline_service import _gerar_video_com_fallback

TIER_ENV_VARS = ("HF_MODEL_PADRAO", "HF_MODEL_KLING_3_0", "HF_MODEL_PROFISSIONAL")


@pytest.fixture
def fresh_registry(monkeypatch):
    for name in TIER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    def load():
        return importlib.reload(registry)

    yield load
    monkeypatch.undo()
    importlib.reload(registry)


@pytest.mark.parametrize(
    ("key", "tier", "application", "fallback"),
    [
        ("seedance_1_5_pro", "Padrão", KLING_3_0_STD_APPLICATION, KLING_3_0_PRO_APPLICATION),
        ("kling_3_0", "Realista", KLING_3_0_PRO_APPLICATION, ""),
        ("veo_3_1", "Profissional", WAN_3_0_PRIME_APPLICATION, KLING_3_0_PRO_APPLICATION),
        ("sora_2", "Padrão", KLING_3_0_STD_APPLICATION, KLING_3_0_PRO_APPLICATION),
        ("sora_2_pro", "Profissional", WAN_3_0_PRIME_APPLICATION, KLING_3_0_PRO_APPLICATION),
    ],
)
def test_tiers_map_to_higgsfield_models(fresh_registry, key, tier, application, fallback) -> None:
    config = fresh_registry().get_model_config(key)

    assert config.key == key
    assert config.tier == tier
    assert config.application == application
    assert config.fallback_application == fallback
    assert find_argument_profile(config.application) is not None


def test_no_tier_points_to_openai(fresh_registry) -> None:
    configs = fresh_registry().VIDEO_MODEL_REGISTRY.values()

    assert not [config.key for config in configs if config.application.startswith("openai:")]


@pytest.mark.parametrize(
    ("env_var", "key"),
    [
        ("HF_MODEL_PADRAO", "seedance_1_5_pro"),
        ("HF_MODEL_KLING_3_0", "kling_3_0"),
        ("HF_MODEL_PROFISSIONAL", "veo_3_1"),
    ],
)
def test_tier_model_can_be_overridden_by_env(fresh_registry, monkeypatch, env_var, key) -> None:
    monkeypatch.setenv(env_var, "vendor/other-model/text-to-video")

    assert fresh_registry().get_model_config(key).application == "vendor/other-model/text-to-video"


def _failure(code: str) -> IntegrationFailure:
    return IntegrationFailure(
        service="higgsfield",
        stage="generating",
        code=code,
        user_message="falhou",
        technical_message=code,
    )


def _generate_with(generators: dict[str, MagicMock], tmp_path: Path):
    config = registry.VideoModelConfig(
        key="veo_3_1",
        label="Profissional",
        tier="Profissional",
        application=WAN_3_0_PRIME_APPLICATION,
        allowed_resolutions=("720p",),
        fallback_application=KLING_3_0_PRO_APPLICATION,
    )
    with patch(
        "webapp.video_generator.create_video_generator",
        side_effect=lambda application, **_kwargs: generators[application],
    ):
        return _gerar_video_com_fallback(
            config,
            "prompt",
            aspecto="9:16",
            resolucao="720p",
            duracao=5,
            output_path=str(tmp_path / "video.mp4"),
            reference_image_url=None,
            reference_image_path=None,
            extra_arguments={},
        )


@pytest.mark.parametrize("code", ["model_blocked", "model_not_found", "provider_unavailable"])
def test_unavailable_model_falls_back_to_kling_pro(tmp_path, code) -> None:
    primary = MagicMock()
    primary.generate.side_effect = _failure(code)
    fallback = MagicMock()
    fallback.generate.return_value.output_path = tmp_path / "video.mp4"

    result = _generate_with(
        {WAN_3_0_PRIME_APPLICATION: primary, KLING_3_0_PRO_APPLICATION: fallback},
        tmp_path,
    )

    assert result == tmp_path / "video.mp4"
    fallback.generate.assert_called_once()


@pytest.mark.parametrize(
    "code",
    ["insufficient_credits", "auth_invalid", "native_resolution_mismatch", "generation_failed"],
)
def test_other_failures_do_not_spend_a_second_generation(tmp_path, code) -> None:
    primary = MagicMock()
    primary.generate.side_effect = _failure(code)
    fallback = MagicMock()

    with pytest.raises(IntegrationFailure) as captured:
        _generate_with(
            {WAN_3_0_PRIME_APPLICATION: primary, KLING_3_0_PRO_APPLICATION: fallback},
            tmp_path,
        )

    assert captured.value.code == code
    fallback.generate.assert_not_called()
