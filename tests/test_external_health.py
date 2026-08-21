from unittest.mock import patch

from scripts.external_health import probe_external_health


def test_elevenlabs_failure_blocks_narrated_job_submission() -> None:
    with patch(
        "scripts.external_health.check_ffmpeg",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_openai",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_higgsfield",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_elevenlabs",
        return_value=(False, "unavailable"),
    ):
        health = probe_external_health()

    assert health.ready_for_submit is False
