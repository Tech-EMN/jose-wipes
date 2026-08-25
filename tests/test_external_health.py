import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts.external_health import _metadata_timestamp, probe_external_health
from scripts.health_check import check_higgsfield, check_openai


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


def test_known_higgsfield_credit_failure_blocks_submission(tmp_path) -> None:
    failed_at = datetime.now(timezone.utc)
    failed_job = tmp_path / "failed"
    failed_job.mkdir()
    (failed_job / "metadata.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "failed_service": "higgsfield",
                "failure_code": "insufficient_credits",
                "user_message": "Sem créditos Higgsfield.",
                "updated_at": failed_at.isoformat(),
                "request": {"video_model": "kling_3_0"},
            }
        ),
        encoding="utf-8",
    )

    with patch(
        "scripts.external_health.check_ffmpeg",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_openai",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_higgsfield",
        return_value=(True, "auth only"),
    ), patch(
        "scripts.external_health.check_elevenlabs",
        return_value=(True, "ok"),
    ):
        health = probe_external_health(jobs_dir=tmp_path)

    higgsfield = health.services["higgsfield_auth"]
    assert health.ready_for_submit is False
    assert higgsfield.ok is False
    assert higgsfield.auth_confirmed is True
    assert higgsfield.submit_confirmed is True
    assert higgsfield.render_confirmed is False
    assert higgsfield.reason == "insufficient_credits"


def test_later_higgsfield_success_clears_credit_failure(tmp_path) -> None:
    failed_at = datetime.now(timezone.utc)
    failed_job = tmp_path / "failed"
    failed_job.mkdir()
    (failed_job / "metadata.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "failed_service": "higgsfield",
                "failure_code": "insufficient_credits",
                "updated_at": failed_at.isoformat(),
                "request": {"video_model": "kling_3_0"},
            }
        ),
        encoding="utf-8",
    )
    completed_job = tmp_path / "completed"
    completed_job.mkdir()
    (completed_job / "metadata.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "updated_at": (failed_at + timedelta(minutes=1)).isoformat(),
                "request": {"video_model": "kling_3_0"},
            }
        ),
        encoding="utf-8",
    )

    with patch(
        "scripts.external_health.check_ffmpeg",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_openai",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_higgsfield",
        return_value=(True, "auth only"),
    ), patch(
        "scripts.external_health.check_elevenlabs",
        return_value=(True, "ok"),
    ):
        health = probe_external_health(jobs_dir=tmp_path)

    assert health.ready_for_submit is True
    assert health.services["higgsfield_auth"].auth_confirmed is False
    assert health.services["higgsfield_auth"].reason == "credentials_configured"


def test_expired_higgsfield_credit_failure_does_not_block_submission(tmp_path) -> None:
    failed_job = tmp_path / "failed"
    failed_job.mkdir()
    (failed_job / "metadata.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "failed_service": "higgsfield",
                "failure_code": "insufficient_credits",
                "updated_at": "2020-01-01T00:00:00+00:00",
                "request": {"video_model": "kling_3_0"},
            }
        ),
        encoding="utf-8",
    )

    with patch(
        "scripts.external_health.check_ffmpeg",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_openai",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_higgsfield",
        return_value=(True, "auth only"),
    ), patch(
        "scripts.external_health.check_elevenlabs",
        return_value=(True, "ok"),
    ):
        health = probe_external_health(jobs_dir=tmp_path)

    assert health.ready_for_submit is True
    assert health.services["higgsfield_auth"].auth_confirmed is False
    assert health.services["higgsfield_auth"].reason == "credentials_configured"


def test_provider_probes_are_cached() -> None:
    with patch(
        "scripts.external_health._probe_cache",
        None,
    ), patch(
        "scripts.external_health.check_ffmpeg",
        return_value=(True, "ok"),
    ) as ffmpeg, patch(
        "scripts.external_health.check_openai",
        return_value=(True, "ok"),
    ) as openai, patch(
        "scripts.external_health.check_higgsfield",
        return_value=(True, "ok"),
    ) as higgsfield, patch(
        "scripts.external_health.check_elevenlabs",
        return_value=(True, "ok"),
    ) as elevenlabs, patch(
        "scripts.external_health.time.monotonic",
        side_effect=[100.0, 101.0],
    ):
        probe_external_health(use_cached_probes=True)
        probe_external_health(use_cached_probes=True)

    assert ffmpeg.call_count == 1
    assert openai.call_count == 1
    assert higgsfield.call_count == 1
    assert elevenlabs.call_count == 1


def test_openai_health_uses_non_generative_model_lookup() -> None:
    model = SimpleNamespace(id="gpt-4.1-mini")
    client = MagicMock()
    client.models.retrieve.return_value = model
    openai = SimpleNamespace(OpenAI=MagicMock(return_value=client))

    with patch("scripts.health_check.OPENAI_API_KEY", "test-key"), patch(
        "scripts.health_check.OPENAI_PLANNER_MODEL",
        "gpt-4.1-mini",
    ), patch.dict(sys.modules, {"openai": openai}):
        ok, message = check_openai()

    assert ok is True
    assert message == "gpt-4.1-mini: acesso confirmado"
    client.models.retrieve.assert_called_once_with("gpt-4.1-mini")


def test_higgsfield_health_only_checks_configured_credentials() -> None:
    with patch("scripts.health_check.HF_API_KEY", "test-key"), patch(
        "scripts.health_check.HF_API_SECRET",
        "test-secret",
    ), patch.dict(sys.modules, {"higgsfield_client": None}):
        ok, message = check_higgsfield()

    assert ok is True
    assert message.startswith("Credenciais configuradas")


def test_external_health_hides_provider_error_details() -> None:
    signed_url = "https://upload.example.com/private-signature"
    with patch(
        "scripts.external_health.check_ffmpeg",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_openai",
        return_value=(False, f"Erro: request failed at {signed_url}"),
    ), patch(
        "scripts.external_health.check_higgsfield",
        return_value=(False, f"Erro: upload failed at {signed_url}"),
    ), patch(
        "scripts.external_health.check_elevenlabs",
        return_value=(False, f"Erro: request failed at {signed_url}"),
    ):
        health = probe_external_health()

    for name in ("openai", "higgsfield_auth", "elevenlabs"):
        assert signed_url not in health.services[name].message


def test_corrupt_metadata_is_ignored_and_unknown_higgsfield_model_is_classified(
    tmp_path,
) -> None:
    corrupt_job = tmp_path / "corrupt"
    corrupt_job.mkdir()
    (corrupt_job / "metadata.json").write_text("{", encoding="utf-8")

    failed_job = tmp_path / "unknown-model"
    failed_job.mkdir()
    (failed_job / "metadata.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "failed_service": "higgsfield",
                "failure_code": "insufficient_credits",
                "updated_at": "invalid-timestamp",
                "request": {"video_model": "unknown-model"},
            }
        ),
        encoding="utf-8",
    )

    with patch(
        "scripts.external_health.check_ffmpeg",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_openai",
        return_value=(True, "ok"),
    ), patch(
        "scripts.external_health.check_higgsfield",
        return_value=(True, "auth only"),
    ), patch(
        "scripts.external_health.check_elevenlabs",
        return_value=(True, "ok"),
    ):
        health = probe_external_health(jobs_dir=tmp_path)

    assert health.ready_for_submit is False
    assert health.services["higgsfield_auth"].reason == "insufficient_credits"


def test_naive_job_timestamp_is_interpreted_as_utc(tmp_path) -> None:
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("{}", encoding="utf-8")

    timestamp = _metadata_timestamp(
        {"updated_at": "2026-08-25T12:00:00"},
        metadata_path,
    )

    assert timestamp == datetime(2026, 8, 25, 12, tzinfo=timezone.utc).timestamp()
