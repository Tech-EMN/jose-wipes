import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from webapp.job_manager import PLAN_FILENAME, JobManager

API_KEY = "test-key"


def _write_job(jobs_dir: Path, job_id: str, created_at: str, *, plan: dict[str, object] | None = None) -> None:
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "metadata.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "status": "completed",
                "created_at": created_at,
                "title": f"Job {job_id}",
                "warnings": ["aviso"],
                "request": {"video_model": "veo_3_1", "resolution": "1080p", "duration_seconds": 30},
            }
        ),
        encoding="utf-8",
    )
    if plan is not None:
        (job_dir / PLAN_FILENAME).write_text(json.dumps(plan), encoding="utf-8")


@pytest.fixture
def manager(tmp_path: Path) -> JobManager:
    jobs_dir = tmp_path / "jobs"
    _write_job(jobs_dir, "older", "2026-10-01T10:00:00+00:00")
    _write_job(jobs_dir, "newest", "2026-10-02T13:00:00+00:00", plan={"title": "Plano", "shots": []})
    _write_job(jobs_dir, "middle", "2026-10-02T09:00:00+00:00")
    (jobs_dir / "sem_metadata").mkdir()
    return JobManager(jobs_dir=jobs_dir)


def test_recent_jobs_are_listed_newest_first_with_request_details(manager: JobManager) -> None:
    jobs = manager.list_recent_jobs(2)

    assert [job.job_id for job in jobs] == ["newest", "middle"]
    assert jobs[0].video_model == "veo_3_1"
    assert jobs[0].resolution == "1080p"
    assert jobs[0].duration_seconds == 30
    assert jobs[0].warnings == ["aviso"]


def test_plan_is_returned_only_when_it_exists(manager: JobManager) -> None:
    assert manager.get_job_plan("newest") == {"title": "Plano", "shots": []}
    assert manager.get_job_plan("older") is None
    with pytest.raises(FileNotFoundError):
        manager.get_job_plan("inexistente")


def test_api_exposes_recent_jobs_and_plans(manager: JobManager) -> None:
    from webapp import main

    with patch.object(main, "job_manager", manager), patch("webapp.auth.API_KEY", API_KEY):
        client = TestClient(main.app, headers={"X-API-Key": API_KEY})
        listing = client.get("/api/jobs", params={"limit": 500})
        plan = client.get("/api/jobs/newest/plan")
        pending = client.get("/api/jobs/older/plan")
        missing = client.get("/api/jobs/inexistente/plan")

    assert listing.status_code == 200
    assert [job["job_id"] for job in listing.json()] == ["newest", "middle", "older"]
    assert plan.json() == {"title": "Plano", "shots": []}
    assert pending.status_code == 409
    assert missing.status_code == 404
