"""Request arguments accepted by each Higgsfield text-to-video model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

KLING_3_0_STD_APPLICATION = "kling-video/v3.0/std/text-to-video"
KLING_3_0_PRO_APPLICATION = "kling-video/v3.0/pro/text-to-video"
KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION = "kling-video/v3.0/pro/image-to-video"
KLING_3_0_STD_IMAGE_TO_VIDEO_APPLICATION = "kling-video/v3.0/std/image-to-video"
WAN_3_0_PRIME_APPLICATION = "alibaba/wan-3.0-prime/text-to-video"
WAN_3_0_PRIME_IMAGE_TO_VIDEO_APPLICATION = "alibaba/wan-3.0-prime/image-to-video"
SOUL_2_APPLICATION = "higgsfield-ai/soul/v2/standard"
SOUL_STANDARD_APPLICATION = "higgsfield-ai/soul/standard"


@dataclass(frozen=True)
class ModelArgumentProfile:
    min_duration_seconds: int
    max_duration_seconds: int
    audio_off_arguments: Mapping[str, object]
    sends_resolution: bool = False
    sends_aspect_ratio: bool = True
    accepts_reference_image: bool = False
    input_image_argument: str | None = None

    def __post_init__(self) -> None:
        if self.min_duration_seconds < 1:
            raise ValueError("min_duration_seconds must be positive")
        if self.min_duration_seconds > self.max_duration_seconds:
            raise ValueError("min_duration_seconds must not exceed max_duration_seconds")

    @property
    def uses_image(self) -> bool:
        return self.accepts_reference_image or self.input_image_argument is not None

    def clamp_duration(self, seconds: int) -> int:
        return max(self.min_duration_seconds, min(seconds, self.max_duration_seconds))

    def build_arguments(
        self,
        *,
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        duration_seconds: int,
        reference_image_url: str | None,
    ) -> dict[str, object]:
        arguments: dict[str, object] = {
            "prompt": prompt,
            "duration": self.clamp_duration(duration_seconds),
            **self.audio_off_arguments,
        }
        if self.sends_aspect_ratio:
            arguments["aspect_ratio"] = aspect_ratio
        if self.sends_resolution:
            arguments["resolution"] = resolution
        if not reference_image_url:
            return arguments
        if self.input_image_argument is not None:
            arguments[self.input_image_argument] = reference_image_url
        elif self.accepts_reference_image:
            arguments["reference_image_urls"] = [reference_image_url]
        return arguments


@dataclass(frozen=True)
class ImageArgumentProfile:
    uses_image: bool = False

    def build_arguments(
        self,
        *,
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        duration_seconds: int,
        reference_image_url: str | None,
    ) -> dict[str, object]:
        return {"prompt": prompt, "aspect_ratio": aspect_ratio, "resolution": resolution}


ArgumentProfile = ModelArgumentProfile | ImageArgumentProfile

SOUL_PROFILE = ImageArgumentProfile()

KLING_3_0_PROFILE = ModelArgumentProfile(
    min_duration_seconds=3,
    max_duration_seconds=15,
    audio_off_arguments=MappingProxyType({"sound": "off"}),
)

KLING_3_0_IMAGE_TO_VIDEO_PROFILE = ModelArgumentProfile(
    min_duration_seconds=3,
    max_duration_seconds=15,
    audio_off_arguments=MappingProxyType({"sound": "off"}),
    sends_aspect_ratio=False,
    input_image_argument="image_url",
)

WAN_3_0_PRIME_PROFILE = ModelArgumentProfile(
    min_duration_seconds=2,
    max_duration_seconds=30,
    audio_off_arguments=MappingProxyType({"generate_audio": False}),
    sends_resolution=True,
)

WAN_3_0_PRIME_IMAGE_TO_VIDEO_PROFILE = ModelArgumentProfile(
    min_duration_seconds=2,
    max_duration_seconds=30,
    audio_off_arguments=MappingProxyType({"generate_audio": False}),
    sends_resolution=True,
    input_image_argument="image_url",
)

MODEL_ARGUMENT_PROFILES: Mapping[str, ArgumentProfile] = MappingProxyType(
    {
        KLING_3_0_STD_APPLICATION: KLING_3_0_PROFILE,
        KLING_3_0_PRO_APPLICATION: KLING_3_0_PROFILE,
        KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION: KLING_3_0_IMAGE_TO_VIDEO_PROFILE,
        KLING_3_0_STD_IMAGE_TO_VIDEO_APPLICATION: KLING_3_0_IMAGE_TO_VIDEO_PROFILE,
        WAN_3_0_PRIME_APPLICATION: WAN_3_0_PRIME_PROFILE,
        WAN_3_0_PRIME_IMAGE_TO_VIDEO_APPLICATION: WAN_3_0_PRIME_IMAGE_TO_VIDEO_PROFILE,
        SOUL_2_APPLICATION: SOUL_PROFILE,
        SOUL_STANDARD_APPLICATION: SOUL_PROFILE,
    }
)


IMAGE_TO_VIDEO_APPLICATIONS: Mapping[str, str] = MappingProxyType(
    {
        KLING_3_0_STD_APPLICATION: KLING_3_0_STD_IMAGE_TO_VIDEO_APPLICATION,
        KLING_3_0_PRO_APPLICATION: KLING_3_0_PRO_IMAGE_TO_VIDEO_APPLICATION,
        WAN_3_0_PRIME_APPLICATION: WAN_3_0_PRIME_IMAGE_TO_VIDEO_APPLICATION,
    }
)


def find_argument_profile(application: str) -> ArgumentProfile | None:
    return MODEL_ARGUMENT_PROFILES.get(application)


def find_image_to_video_application(application: str) -> str | None:
    return IMAGE_TO_VIDEO_APPLICATIONS.get(application)
