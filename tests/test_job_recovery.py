"""Job claiming and recovery of jobs abandoned by a stopped worker."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from jose_wipes.jobs.job_claim import ClaimHeartbeat, claim_age_seconds, claim_path, try_claim
from jose_wipes.jobs.job_manager import FilePollingJobManager, JobManager, INTERRUPTED_FAILURE_CODE
from jose_wipes.schemas import CreateJobRequest, PlannerOutput, PlannerShot, ProductOverlayConfig

STALE_AFTER_SECONDS = 60
OLD_TIMESTAMP_OFFSET_SECONDS = 3600
JOB_TIMEOUT_SECONDS = 10


def _make_request() -> CreateJobRequest:
    return CreateJobRequest.model_validate({
        "resolution": "720p",
        "orientation": "vertical",
        "duration_seconds": 10,
        "prompt": "Test prompt for job recovery",
        "video_model": "seedance_1_5_pro",
    })


def _fake_planner(request, pdf_text, model_config, *, artifacts_dir=None):
    return PlannerOutput(
        title="Recovery",
        enhanced_brief_pt="Briefing",
        global_style="Comercial",
        final_cta_pt="CTA",
        notes="",
        shots=[
            PlannerShot(
                shot_number=1,
                visual_prompt_en="Premium bathroom commercial lighting with confident hero.",
                duration_seconds=5,
                narration_text_pt="Linha",
                voice_persona="narrador",
                overlay_text="Texto",
                product_overlay=ProductOverlayConfig(),
            )
        ],
    )


class _CountingRenderer:
    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self, *, job_dir, **kwargs):
        with self._lock:
            self.calls += 1
        final_video = Path(job_dir) / "final.mp4"
        final_video.write_bytes(b"video")
        return {"final_video_path": str(final_video), "warnings": []}


def _manager(tmp_path: Path, renderer=None) -> JobManager:
    return JobManager(
        jobs_dir=tmp_path,
        planner_fn=_fake_planner,
        renderer_fn=renderer or _CountingRenderer(),
        heartbeat_seconds=0.05,
        stale_after_seconds=STALE_AFTER_SECONDS,
    )


def _set_status(job_dir: Path, status: str) -> None:
    metadata_path = job_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["status"] = status
    metadata["step"] = status
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")


def _status(job_dir: Path) -> dict[str, object]:
    return json.loads((job_dir / "metadata.json").read_text(encoding="utf-8"))


def _age_claim(job_dir: Path) -> None:
    old = time.time() - OLD_TIMESTAMP_OFFSET_SECONDS
    os.utime(claim_path(job_dir), (old, old))


def _wait_for_status(job_dir: Path, expected: str) -> bool:
    deadline = time.time() + JOB_TIMEOUT_SECONDS
    while time.time() < deadline:
        if _status(job_dir)["status"] == expected:
            return True
        time.sleep(0.05)
    return False


class TestClaim:
    def test_only_first_claim_wins(self, tmp_path):
        assert try_claim(tmp_path) is True
        assert try_claim(tmp_path) is False

    def test_claim_age_is_none_without_claim(self, tmp_path):
        assert claim_age_seconds(tmp_path) is None

    def test_heartbeat_keeps_claim_fresh(self, tmp_path):
        try_claim(tmp_path)
        _age_claim(tmp_path)
        with ClaimHeartbeat(tmp_path, interval_seconds=0.05):
            time.sleep(0.3)
        assert claim_age_seconds(tmp_path) < STALE_AFTER_SECONDS


class TestRecovery:
    def test_in_progress_job_without_claim_is_failed(self, tmp_path):
        manager = _manager(tmp_path)
        job_dir = tmp_path / manager.create_job(_make_request())["job_id"]
        _set_status(job_dir, "planning")

        assert manager.recover_interrupted_jobs() == [job_dir.name]

        stored = _status(job_dir)
        assert stored["status"] == "failed"
        assert stored["failure_code"] == INTERRUPTED_FAILURE_CODE
        assert stored["failed_stage"] == "planning"
        assert stored["failed_service"] == "worker"
        assert stored["retryable"] is True

    def test_in_progress_job_with_stale_claim_is_failed(self, tmp_path):
        manager = _manager(tmp_path)
        job_dir = tmp_path / manager.create_job(_make_request())["job_id"]
        try_claim(job_dir)
        _set_status(job_dir, "generating")
        _age_claim(job_dir)

        assert manager.recover_interrupted_jobs() == [job_dir.name]
        assert _status(job_dir)["failed_stage"] == "generating"

    def test_in_progress_job_with_fresh_claim_is_kept(self, tmp_path):
        manager = _manager(tmp_path)
        job_dir = tmp_path / manager.create_job(_make_request())["job_id"]
        try_claim(job_dir)
        _set_status(job_dir, "composing")

        assert manager.recover_interrupted_jobs() == []
        assert _status(job_dir)["status"] == "composing"

    def test_queued_job_without_claim_is_kept(self, tmp_path):
        manager = _manager(tmp_path)
        job_dir = tmp_path / manager.create_job(_make_request())["job_id"]

        assert manager.recover_interrupted_jobs() == []
        assert _status(job_dir)["status"] == "queued"

    def test_queued_job_with_stale_claim_is_failed(self, tmp_path):
        manager = _manager(tmp_path)
        job_dir = tmp_path / manager.create_job(_make_request())["job_id"]
        try_claim(job_dir)
        _age_claim(job_dir)

        assert manager.recover_interrupted_jobs() == [job_dir.name]
        assert _status(job_dir)["failed_stage"] == "queued"

    def test_terminal_jobs_are_kept(self, tmp_path):
        manager = _manager(tmp_path)
        completed = tmp_path / manager.create_job(_make_request())["job_id"]
        failed = tmp_path / manager.create_job(_make_request())["job_id"]
        _set_status(completed, "completed")
        _set_status(failed, "failed")

        assert manager.recover_interrupted_jobs() == []
        assert _status(completed)["status"] == "completed"
        assert _status(failed)["status"] == "failed"

    def test_unreadable_metadata_is_skipped(self, tmp_path):
        manager = _manager(tmp_path)
        broken = tmp_path / "broken"
        broken.mkdir()
        (broken / "metadata.json").write_text("{", encoding="utf-8")

        assert manager.recover_interrupted_jobs() == []


class TestExclusiveProcessing:
    def test_claimed_job_is_not_discovered(self, tmp_path):
        manager = _manager(tmp_path)
        job_dir = tmp_path / manager.create_job(_make_request())["job_id"]
        try_claim(job_dir)

        assert manager._discover_queued_jobs() == []

    def test_job_is_processed_only_once(self, tmp_path):
        renderer = _CountingRenderer()
        manager = _manager(tmp_path, renderer)
        job_id = manager.create_job(_make_request())["job_id"]

        assert manager._execute_job(job_id) is True
        assert manager._execute_job(job_id) is False
        assert renderer.calls == 1
        assert _status(tmp_path / job_id)["status"] == "completed"

    def test_two_polling_workers_process_each_job_once(self, tmp_path):
        renderer = _CountingRenderer()
        creator = _manager(tmp_path, renderer)
        job_ids = [creator.create_job(_make_request())["job_id"] for _ in range(4)]
        workers = [
            FilePollingJobManager(
                jobs_dir=tmp_path,
                poll_interval=0.05,
                planner_fn=_fake_planner,
                renderer_fn=renderer,
                heartbeat_seconds=0.05,
                stale_after_seconds=STALE_AFTER_SECONDS,
            )
            for _ in range(2)
        ]
        for worker in workers:
            worker.start()
        try:
            for job_id in job_ids:
                assert _wait_for_status(tmp_path / job_id, "completed")
        finally:
            for worker in workers:
                worker.stop()

        assert renderer.calls == len(job_ids)


class TestStartup:
    def test_in_process_manager_resumes_queued_jobs_from_disk(self, tmp_path):
        previous = _manager(tmp_path)
        job_id = previous.create_job(_make_request())["job_id"]

        restarted = _manager(tmp_path)
        restarted.start()
        try:
            assert _wait_for_status(tmp_path / job_id, "completed")
        finally:
            restarted.stop()

    def test_polling_worker_fails_job_abandoned_by_previous_worker(self, tmp_path):
        creator = _manager(tmp_path)
        job_dir = tmp_path / creator.create_job(_make_request())["job_id"]
        try_claim(job_dir)
        _set_status(job_dir, "generating")
        _age_claim(job_dir)

        worker = FilePollingJobManager(
            jobs_dir=tmp_path,
            poll_interval=0.05,
            planner_fn=_fake_planner,
            renderer_fn=_CountingRenderer(),
            stale_after_seconds=STALE_AFTER_SECONDS,
        )
        worker.start()
        try:
            assert _wait_for_status(job_dir, "failed")
        finally:
            worker.stop()
        assert _status(job_dir)["failure_code"] == INTERRUPTED_FAILURE_CODE
