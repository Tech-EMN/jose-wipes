"""Retrying a failed job resumes it instead of starting over."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from jose_wipes.integrations.errors import IntegrationFailure
from jose_wipes.jobs.job_claim import claim_path
from jose_wipes.jobs.job_manager import INTERRUPTED_FAILURE_CODE, JOB_NOT_FAILED_CODE, JobManager
from jose_wipes.result import Err, Ok
from jose_wipes.schemas import CreateJobRequest, PlannerOutput, PlannerShot

API_KEY = "test-key"
PLANNING_WARNING = "aviso do planejamento"
RENDER_WARNING = "aviso do render"


def _request() -> CreateJobRequest:
    return CreateJobRequest(
        resolution="720p",
        orientation="vertical",
        duration_seconds=10,
        prompt="Cena institucional",
        video_model="kling_3_0",
    )


class _Planner:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request, pdf_text, model_config, *, artifacts_dir=None) -> PlannerOutput:
        self.calls += 1
        return PlannerOutput(
            title="Retomada",
            enhanced_brief_pt="Briefing",
            global_style="Minimalista",
            final_cta_pt="CTA",
            shots=[PlannerShot(shot_number=1, visual_prompt_en="A clean studio scene.")],
        )


class _FlakyRenderer:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def __call__(self, *, job_dir: Path, **kwargs) -> dict[str, object]:
        self.calls += 1
        if self.calls <= self.failures:
            raise IntegrationFailure(
                service="google_drive",
                stage="uploading_drive",
                code="drive_upload_failed",
                user_message="Falha ao entregar o vídeo final no Google Drive.",
                retryable=True,
            )
        final_video = job_dir / "final.mp4"
        final_video.write_bytes(b"video")
        return {"final_video_path": str(final_video), "warnings": [RENDER_WARNING]}


def _failed_job(tmp_path: Path) -> tuple[JobManager, str, _Planner, _FlakyRenderer]:
    planner = _Planner()
    renderer = _FlakyRenderer(failures=1)
    manager = JobManager(jobs_dir=tmp_path / "jobs", planner_fn=planner, renderer_fn=renderer)
    job_id = str(manager.create_job(_request())["job_id"])
    manager._update_job(job_id, warnings=[PLANNING_WARNING])
    assert manager.run_now(job_id).status == "failed"
    return manager, job_id, planner, renderer


def test_retry_reuses_the_plan_and_renders_again(tmp_path: Path) -> None:
    manager, job_id, planner, renderer = _failed_job(tmp_path)

    retried = manager.retry_job(job_id)
    assert isinstance(retried, Ok)
    assert retried.value.status == "queued"
    assert retried.value.failure_code is None
    assert retried.value.retry_count == 1

    final = manager.run_now(job_id)

    assert final.status == "completed"
    assert planner.calls == 1
    assert renderer.calls == 2
    assert final.warnings == [PLANNING_WARNING, RENDER_WARNING]


def test_retry_releases_the_claim_so_a_worker_can_take_the_job(tmp_path: Path) -> None:
    manager, job_id, _, _ = _failed_job(tmp_path)
    assert claim_path(manager.jobs_dir / job_id).exists()

    manager.retry_job(job_id)

    assert not claim_path(manager.jobs_dir / job_id).exists()
    assert manager._discover_queued_jobs() == [job_id]


def test_retry_rejects_a_job_that_did_not_fail(tmp_path: Path) -> None:
    manager = JobManager(jobs_dir=tmp_path / "jobs", planner_fn=_Planner(), renderer_fn=_FlakyRenderer(0))
    job_id = str(manager.create_job(_request())["job_id"])

    result = manager.retry_job(job_id)

    assert isinstance(result, Err)
    assert result.failure.code == JOB_NOT_FAILED_CODE
    assert manager.get_job_status(job_id).status == "queued"


@pytest.mark.parametrize("job_id", ["..", "inexistente", "0" * 32])
def test_retry_of_unknown_or_malformed_job_is_not_found(tmp_path: Path, job_id: str) -> None:
    manager = JobManager(jobs_dir=tmp_path / "jobs")

    with pytest.raises(FileNotFoundError):
        manager.retry_job(job_id)


def test_job_interrupted_by_a_stopped_worker_can_be_retried(tmp_path: Path) -> None:
    planner = _Planner()
    renderer = _FlakyRenderer(failures=0)
    manager = JobManager(
        jobs_dir=tmp_path / "jobs",
        planner_fn=planner,
        renderer_fn=renderer,
        stale_after_seconds=0,
    )
    job_id = str(manager.create_job(_request())["job_id"])
    manager._update_job(job_id, status="generating")
    assert manager.recover_interrupted_jobs() == [job_id]
    assert manager.get_job_status(job_id).failure_code == INTERRUPTED_FAILURE_CODE

    assert isinstance(manager.retry_job(job_id), Ok)
    assert manager.run_now(job_id).status == "completed"


def test_retry_endpoint(tmp_path: Path) -> None:
    from webapp import main

    manager, failed_id, _, _ = _failed_job(tmp_path)
    queued_id = str(manager.create_job(_request())["job_id"])

    with patch.object(main, "job_manager", manager), patch("webapp.auth.API_KEY", API_KEY):
        client = TestClient(main.app, headers={"X-API-Key": API_KEY})
        accepted = client.post(f"/api/jobs/{failed_id}/retry")
        conflict = client.post(f"/api/jobs/{queued_id}/retry")
        missing = client.post(f"/api/jobs/{'f' * 32}/retry")

    assert accepted.status_code == 202
    assert accepted.json()["status"] == "queued"
    assert conflict.status_code == 409
    assert missing.status_code == 404
