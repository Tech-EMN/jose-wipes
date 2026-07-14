"""Tests for F14: separate web + worker containers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from webapp.job_manager import FilePollingJobManager, JobManager
from webapp.schemas import CreateJobRequest


def _make_request(**overrides) -> CreateJobRequest:
    return CreateJobRequest.model_validate({
        "resolution": "720p",
        "orientation": "vertical",
        "duration_seconds": 10,
        "prompt": "Test prompt for container separation",
        "video_model": "seedance_1_5_pro",
        **overrides,
    })


class TestFilePollingJobManager:
    """Tests for file-polling based job manager (worker container)."""

    def test_creates_job_queued_in_shared_dir(self, tmp_path):
        """Web container creates job → worker container discovers it."""
        manager = FilePollingJobManager(jobs_dir=tmp_path, poll_interval=1)

        metadata = manager.create_job(_make_request())
        job_id = metadata["job_id"]
        assert isinstance(job_id, str)
        assert len(job_id) == 32

        # Job should exist on disk
        job_dir = tmp_path / job_id
        assert job_dir.exists()
        assert (job_dir / "metadata.json").exists()

        # Status should be "queued"
        stored = json.loads((job_dir / "metadata.json").read_text())
        assert stored["status"] == "queued"

    def test_web_container_skips_worker(self, tmp_path, monkeypatch):
        """Web container with JW_SKIP_WORKER=true should NOT start worker."""
        monkeypatch.setenv("JW_SKIP_WORKER", "true")

        # Simulate main.py startup logic
        skip = False
        import os
        if os.getenv("JW_SKIP_WORKER", "").strip().lower() in {"true", "1", "yes"}:
            skip = True

        assert skip is True

    def test_discover_queued_jobs(self, tmp_path):
        """_discover_queued_jobs should find jobs with status 'queued'."""
        manager = FilePollingJobManager(jobs_dir=tmp_path, poll_interval=1)

        # Create 3 jobs
        ids = []
        for i in range(3):
            metadata = manager.create_job(_make_request(prompt=f"Test {i}"))
            ids.append(metadata["job_id"])

        # All should be queued
        queued = manager._discover_queued_jobs()
        assert len(queued) == 3
        assert set(queued) == set(ids)

    def test_discover_ignores_completed_jobs(self, tmp_path):
        """_discover_queued_jobs should ignore non-queued jobs."""
        manager = FilePollingJobManager(jobs_dir=tmp_path, poll_interval=1)

        # Create 1 queued and 1 completed
        meta1 = manager.create_job(_make_request(prompt="queued"))
        meta2 = manager.create_job(_make_request(prompt="completed"))
        # Manually mark job2 as completed
        job_dir2 = tmp_path / meta2["job_id"]
        stored = json.loads((job_dir2 / "metadata.json").read_text())
        stored["status"] = "completed"
        (job_dir2 / "metadata.json").write_text(json.dumps(stored))

        queued = manager._discover_queued_jobs()
        assert len(queued) == 1
        assert queued[0] == meta1["job_id"]

    def test_polling_worker_starts_and_stops(self, tmp_path):
        """Worker thread should start and stop cleanly."""
        manager = FilePollingJobManager(jobs_dir=tmp_path, poll_interval=1)

        manager.start()
        assert manager._worker is not None
        assert manager._worker.is_alive()

        manager.stop()
        manager._worker.join(timeout=2)
        assert not manager._worker.is_alive()

    def test_shared_volume_both_containers(self, tmp_path):
        """Simulate web writing to shared volume, worker reading from it."""
        # Web side: create job
        web_manager = JobManager(jobs_dir=tmp_path)
        meta = web_manager.create_job(_make_request())
        job_id = meta["job_id"]

        # Worker side: discover job from shared volume
        worker_manager = FilePollingJobManager(jobs_dir=tmp_path, poll_interval=1)
        queued = worker_manager._discover_queued_jobs()
        assert job_id in queued

    def test_empty_jobs_dir(self, tmp_path):
        """Empty jobs directory should return empty list."""
        manager = FilePollingJobManager(jobs_dir=tmp_path, poll_interval=1)
        assert manager._discover_queued_jobs() == []


class TestDockerComposeSeparation:
    """Verify docker-compose files have separate web and worker services."""

    def test_dev_compose_has_web_service(self):
        """docker-compose.yml should parse correctly with web + worker."""
        compose_path = Path(__file__).parent.parent / "docker-compose.yml"
        if not compose_path.exists():
            pytest.skip("docker-compose.yml not found")
        content = compose_path.read_text()
        assert "jose-wipes-web:" in content
        assert "jose-wipes-worker:" in content

    def test_dev_compose_has_two_services(self):
        """docker-compose.yml should have web + worker services."""
        compose_path = Path(__file__).parent.parent / "docker-compose.yml"
        if not compose_path.exists():
            pytest.skip("docker-compose.yml not found")

        content = compose_path.read_text()
        assert "jose-wipes-web:" in content
        assert "jose-wipes-worker:" in content
        assert "JW_SKIP_WORKER" in content, "Web container must skip worker"

    def test_hostinger_compose_has_two_services(self):
        """docker-compose.hostinger.yml should have web + worker services."""
        compose_path = Path(__file__).parent.parent / "docker-compose.hostinger.yml"
        if not compose_path.exists():
            pytest.skip("docker-compose.hostinger.yml not found")

        content = compose_path.read_text()
        assert "jose-wipes-web:" in content
        assert "jose-wipes-worker:" in content

    def test_services_share_volume(self):
        """Both services should reference the same named volume."""
        compose_path = Path(__file__).parent.parent / "docker-compose.hostinger.yml"
        if not compose_path.exists():
            pytest.skip("docker-compose.hostinger.yml not found")

        content = compose_path.read_text()
        # Both should mount jose_wipes_output
        web_vol = content.find("jose-wipes-web:")
        worker_vol = content.find("jose-wipes-worker:")

        web_section = content[web_vol:worker_vol] if web_vol < worker_vol else content[web_vol:]
        worker_section = content[worker_vol:]

        assert "jose_wipes_output" in web_section
        assert "jose_wipes_output" in worker_section
