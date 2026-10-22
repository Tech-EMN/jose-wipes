"""CLI and QA runner go through the same moderation, planner and renderer as the web."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.pipeline as cli
import jose_wipes.jobs.job_manager as job_manager_module
from jose_wipes.integrations.errors import IntegrationFailure
from jose_wipes.moderation import ModerationResult
from jose_wipes.schemas import CreateJobRequest, PlannerOutput

FIXTURE_PLAN = Path(__file__).parent / "fixtures" / "e2e_web_plan.json"


def _request(prompt: str = "Vídeo de teste do pipeline único") -> CreateJobRequest:
    return CreateJobRequest(
        resolution="720p",
        orientation="vertical",
        duration_seconds=10,
        prompt=prompt,
        video_model="seedance_1_5_pro",
    )


def _fixture_plan() -> PlannerOutput:
    return PlannerOutput.model_validate_json(FIXTURE_PLAN.read_text(encoding="utf-8"))


class _Recorder:
    def __init__(self) -> None:
        self.planner_calls = 0
        self.render_calls: list[dict[str, object]] = []

    def planner(self, request, pdf_text, model_config, *, artifacts_dir=None) -> PlannerOutput:
        self.planner_calls += 1
        return _fixture_plan()

    def renderer(self, *, job_dir, **kwargs) -> dict[str, object]:
        self.render_calls.append(kwargs)
        final_video = Path(job_dir) / "final" / "video.mp4"
        final_video.parent.mkdir(parents=True, exist_ok=True)
        final_video.write_bytes(b"video")
        return {"final_video_path": str(final_video), "drive_url": "https://drive/x", "warnings": []}


@pytest.fixture
def recorder(monkeypatch) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(job_manager_module, "plan_web_video", recorder.planner)
    monkeypatch.setattr(job_manager_module, "render_planned_video", recorder.renderer)
    monkeypatch.setattr(cli, "moderate_prompt_sync", lambda prompt: ModerationResult(allowed=True))
    return recorder


def test_run_pipeline_uses_production_planner_and_renderer(tmp_path, recorder):
    run = cli.run_pipeline(_request(), jobs_dir=tmp_path)

    assert run.succeeded
    assert recorder.planner_calls == 1
    assert len(recorder.render_calls) == 1
    assert run.final_video_path.exists()
    assert run.status.drive_url == "https://drive/x"
    metadata = json.loads((tmp_path / run.job_id / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "completed"
    assert metadata["request"]["prompt"] == "Vídeo de teste do pipeline único"


def test_run_pipeline_with_plan_skips_planner(tmp_path, recorder):
    plan = _fixture_plan()

    run = cli.run_pipeline(_request(), plan=plan, jobs_dir=tmp_path)

    assert run.succeeded
    assert recorder.planner_calls == 0
    assert recorder.render_calls[0]["plan"] == plan


def test_run_pipeline_passes_web_options_to_renderer(tmp_path, recorder):
    cli.run_pipeline(
        _request(),
        jobs_dir=tmp_path,
        apply_logo_overlay=False,
        use_product_reference=False,
    )

    call = recorder.render_calls[0]
    assert call["apply_logo_overlay"] is False
    assert call["use_product_reference"] is False


def test_run_pipeline_stops_at_moderation(tmp_path, recorder, monkeypatch):
    monkeypatch.setattr(
        cli,
        "moderate_prompt_sync",
        lambda prompt: ModerationResult(allowed=False, reason="Prompt bloqueado."),
    )

    run = cli.run_pipeline(_request(), jobs_dir=tmp_path)

    assert not run.succeeded
    assert run.blocked_reason == "Prompt bloqueado."
    assert run.job_id is None
    assert list(tmp_path.iterdir()) == []


def test_run_pipeline_reports_render_failure(tmp_path, recorder, monkeypatch):
    def failing_renderer(**kwargs):
        raise IntegrationFailure(
            service="higgsfield",
            stage="generating",
            code="insufficient_credits",
            user_message="Sem créditos.",
            retryable=False,
        )

    monkeypatch.setattr(job_manager_module, "render_planned_video", failing_renderer)

    run = cli.run_pipeline(_request(), jobs_dir=tmp_path)

    assert not run.succeeded
    assert run.status.status == "failed"
    assert run.status.failure_code == "insufficient_credits"


def test_progress_listener_receives_status_changes(tmp_path, recorder):
    statuses: list[str] = []

    cli.run_pipeline(
        _request(),
        jobs_dir=tmp_path,
        on_progress=lambda job_id, metadata: statuses.append(str(metadata["status"])),
    )

    assert statuses[0] == "planning"
    assert statuses[-1] == "completed"


def test_main_runs_saved_plan_and_returns_success(tmp_path, recorder, monkeypatch):
    monkeypatch.setattr(job_manager_module, "OUTPUT_DIR", tmp_path)

    exit_code = cli.main(["--plano", str(FIXTURE_PLAN), "--duracao", "10", "--sem-logo"])

    assert exit_code == cli.EXIT_SUCCESS
    assert recorder.planner_calls == 0
    assert recorder.render_calls[0]["apply_logo_overlay"] is False


def test_main_without_input_returns_usage_error(capsys):
    assert cli.main([]) == cli.EXIT_USAGE
