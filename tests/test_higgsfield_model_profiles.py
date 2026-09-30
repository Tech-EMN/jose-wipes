import pytest

from scripts.higgsfield_model_profiles import (
    KLING_3_0_PRO_APPLICATION,
    KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION,
    KLING_3_0_STD_APPLICATION,
    SOUL_2_APPLICATION,
    SOUL_STANDARD_APPLICATION,
    WAN_3_0_PRIME_APPLICATION,
    ModelArgumentProfile,
    find_argument_profile,
)

REFERENCE_URL = "https://example.com/product.png"


def _arguments(application: str, *, duration_seconds: int = 5) -> dict[str, object]:
    profile = find_argument_profile(application)
    assert profile is not None
    return profile.build_arguments(
        prompt="A man in a gym locker room.",
        aspect_ratio="9:16",
        resolution="1080p",
        duration_seconds=duration_seconds,
        reference_image_url=REFERENCE_URL,
    )


@pytest.mark.parametrize("application", [KLING_3_0_STD_APPLICATION, KLING_3_0_PRO_APPLICATION])
def test_kling_3_turns_native_sound_off_and_skips_unsupported_fields(application: str) -> None:
    assert _arguments(application) == {
        "prompt": "A man in a gym locker room.",
        "aspect_ratio": "9:16",
        "duration": 5,
        "sound": "off",
    }


def test_wan_3_prime_sends_resolution_and_disables_generated_audio() -> None:
    assert _arguments(WAN_3_0_PRIME_APPLICATION) == {
        "prompt": "A man in a gym locker room.",
        "aspect_ratio": "9:16",
        "duration": 5,
        "generate_audio": False,
        "resolution": "1080p",
    }


@pytest.mark.parametrize(
    ("application", "requested", "expected"),
    [
        (KLING_3_0_PRO_APPLICATION, 1, 3),
        (KLING_3_0_PRO_APPLICATION, 3, 3),
        (KLING_3_0_PRO_APPLICATION, 15, 15),
        (KLING_3_0_PRO_APPLICATION, 40, 15),
        (WAN_3_0_PRIME_APPLICATION, 1, 2),
        (WAN_3_0_PRIME_APPLICATION, 2, 2),
        (WAN_3_0_PRIME_APPLICATION, 30, 30),
        (WAN_3_0_PRIME_APPLICATION, 45, 30),
    ],
)
def test_duration_is_clamped_to_model_range(application: str, requested: int, expected: int) -> None:
    assert _arguments(application, duration_seconds=requested)["duration"] == expected


def test_reference_image_is_sent_only_when_profile_accepts_it() -> None:
    profile = ModelArgumentProfile(
        min_duration_seconds=1,
        max_duration_seconds=10,
        audio_off_arguments={},
        accepts_reference_image=True,
    )

    arguments = profile.build_arguments(
        prompt="p",
        aspect_ratio="9:16",
        resolution="720p",
        duration_seconds=5,
        reference_image_url=REFERENCE_URL,
    )

    assert arguments["reference_image_urls"] == [REFERENCE_URL]


def test_unknown_application_has_no_profile() -> None:
    assert find_argument_profile("kling-video/v2.1/master/text-to-video") is None


@pytest.mark.parametrize(("minimum", "maximum"), [(0, 5), (6, 5)])
def test_invalid_duration_range_is_rejected(minimum: int, maximum: int) -> None:
    with pytest.raises(ValueError):
        ModelArgumentProfile(
            min_duration_seconds=minimum,
            max_duration_seconds=maximum,
            audio_off_arguments={},
        )


def test_kling_3_image_to_video_sends_input_image_without_aspect_ratio() -> None:
    assert _arguments(KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION) == {
        "prompt": "A man in a gym locker room.",
        "duration": 5,
        "sound": "off",
        "image_url": REFERENCE_URL,
    }


@pytest.mark.parametrize("application", [SOUL_2_APPLICATION, SOUL_STANDARD_APPLICATION])
def test_soul_image_models_send_only_supported_fields(application: str) -> None:
    profile = find_argument_profile(application)

    assert profile is not None
    assert profile.uses_image is False
    assert _arguments(application) == {
        "prompt": "A man in a gym locker room.",
        "aspect_ratio": "9:16",
        "resolution": "1080p",
    }
