"""Single-worker, file-backed async job manager for the web studio."""

from __future__ import annotations

import json
import queue
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from scripts.config import OUTPUT_DIR
from scripts.integration_errors import IntegrationFailure, build_generic_failure
from webapp.model_registry import get_model_config
from webapp.pdf_utils import extract_pdf_text
from webapp.pipeline_service import render_planned_video
from webapp.planner import plan_web_video
from webapp.schemas import CreateJobRequest, JobStatusResponse


PlannerFn = Callable[..., object]
RendererFn = Callable[..., dict[str, object]]


class JobManager:
    """Queue-backed single worker that persists job state on disk."""

    def __init__(
        self,
        jobs_dir: Path | None = None,
        planner_fn: PlannerFn | None = None,
        renderer_fn: RendererFn | None = None,
    ) -> None:
        self.jobs_dir = Path(jobs_dir) if jobs_dir else OUTPUT_DIR / "web_jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.planner_fn = planner_fn or plan_web_video
        self.renderer_fn = renderer_fn or render_planned_video
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the single background worker if it is not already running."""

        if self._worker and self._worker.is_alive():
            return

        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run_worker,
            name="jose-wipes-web-worker",
            daemon=True,
        )
        self._worker.start()

    def stop(self) -> None:
        """Stop the worker thread."""

        self._stop_event.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2)

    def create_job(
        self,
        request: CreateJobRequest,
        *,
        script_pdf_bytes: bytes | None = None,
        script_pdf_name: str | None = None,
        ref_embalagem_bytes: bytes | None = None,
        ref_embalagem_name: str | None = None,
        ref_logo_bytes: bytes | None = None,
        ref_logo_name: str | None = None,
        ref_cores_bytes: bytes | None = None,
        ref_cores_name: str | None = None,
        apply_logo_overlay: bool = True,
    ) -> dict[str, object]:
        """Persist a new job and enqueue it for processing."""

        job_id = uuid.uuid4().hex
        job_dir = self.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        (job_dir / "prompt.txt").write_text(request.prompt, encoding="utf-8")

        pdf_path = None
        if script_pdf_bytes:
            pdf_name = script_pdf_name or "roteiro.pdf"
            pdf_path = job_dir / pdf_name
            pdf_path.write_bytes(script_pdf_bytes)

        # Save reference images
        ref_paths: dict[str, str | None] = {
            "embalagem": None,
            "logo": None,
            "cores": None,
        }

        if ref_embalagem_bytes:
            ext = Path(ref_embalagem_name or "embalagem.png").suffix or ".png"
            emb_path = job_dir / f"ref_embalagem{ext}"
            emb_path.write_bytes(ref_embalagem_bytes)
            ref_paths["embalagem"] = str(emb_path)

        if ref_logo_bytes:
            ext = Path(ref_logo_name or "logo.png").suffix or ".png"
            logo_path = job_dir / f"ref_logo{ext}"
            logo_path.write_bytes(ref_logo_bytes)
            ref_paths["logo"] = str(logo_path)

        if ref_cores_bytes:
            ext = Path(ref_cores_name or "cores.png").suffix or ".png"
            cores_path = job_dir / f"ref_cores{ext}"
            cores_path.write_bytes(ref_cores_bytes)
            ref_paths["cores"] = str(cores_path)

        metadata = {
            "job_id": job_id,
            "status": "queued",
            "step": "queued",
            "progress_message": "Job criado e aguardando processamento.",
            "warnings": [],
            "title": None,
            "enhanced_brief": None,
            "preview_url": None,
            "download_url": None,
            "error_message": None,
            "failed_stage": None,
            "failed_service": None,
            "failure_code": None,
            "retryable": None,
            "user_message": None,
            "auth_confirmed": None,
            "submit_confirmed": None,
            "render_confirmed": None,
            "failure_reason": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "request": request.model_dump(),
            "script_pdf_path": str(pdf_path) if pdf_path else None,
            "ref_embalagem_path": ref_paths["embalagem"],
            "ref_logo_path": ref_paths["logo"],
            "ref_cores_path": ref_paths["cores"],
            "apply_logo_overlay": apply_logo_overlay,
        }

        self._write_metadata(job_dir, metadata)
        self._queue.put(job_id)
        return metadata

    def get_job_status(self, job_id: str) -> JobStatusResponse:
        """Load a job status from disk."""

        metadata = self._read_metadata(self._job_dir(job_id))
        return JobStatusResponse.model_validate(
            {
                "job_id": metadata["job_id"],
                "status": metadata["status"],
                "step": metadata["step"],
                "progress_message": metadata["progress_message"],
                "warnings": metadata.get("warnings", []),
                "title": metadata.get("title"),
                "enhanced_brief": metadata.get("enhanced_brief"),
                "preview_url": metadata.get("preview_url"),
                "download_url": metadata.get("download_url"),
                "error_message": metadata.get("error_message"),
                "failed_stage": metadata.get("failed_stage"),
                "failed_service": metadata.get("failed_service"),
                "failure_code": metadata.get("failure_code"),
                "retryable": metadata.get("retryable"),
                "user_message": metadata.get("user_message"),
                "auth_confirmed": metadata.get("auth_confirmed"),
                "submit_confirmed": metadata.get("submit_confirmed"),
                "render_confirmed": metadata.get("render_confirmed"),
                "failure_reason": metadata.get("failure_reason"),
            }
        )

    def get_download_path(self, job_id: str) -> Path | None:
        """Return the completed final video path, if available."""

        metadata = self._read_metadata(self._job_dir(job_id))
        final_video_path = metadata.get("final_video_path")
        if not final_video_path:
            return None
        path = Path(final_video_path)
        return path if path.exists() else None

    def _run_worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._process_job(job_id)
            finally:
                self._queue.task_done()

    def _process_job(self, job_id: str) -> None:
        job_dir = self._job_dir(job_id)
        metadata = self._read_metadata(job_dir)
        request = CreateJobRequest.model_validate(metadata["request"])
        model_config = get_model_config(request.video_model)

        pdf_text = ""
        warnings = list(metadata.get("warnings", []))
        current_stage = "queued"

        try:
            script_pdf_path = metadata.get("script_pdf_path")
            if script_pdf_path:
                current_stage = "extracting_pdf"
                self._update_job(
                    job_id,
                    status="extracting_pdf",
                    step="extracting_pdf",
                    progress_message="Extraindo texto do PDF enviado...",
                )
                pdf_text, pdf_warnings = extract_pdf_text(Path(script_pdf_path))
                warnings.extend(pdf_warnings)
                if pdf_text:
                    (job_dir / "roteiro_extraido.txt").write_text(pdf_text, encoding="utf-8")
                self._update_job(job_id, warnings=warnings)

            current_stage = "planning"
            self._update_job(
                job_id,
                status="planning",
                step="planning",
                progress_message="Planejando shots e narrações com OpenAI...",
            )

            _MAX_PLANNING_ATTEMPTS = 3
            plan = None
            for _attempt in range(1, _MAX_PLANNING_ATTEMPTS + 1):
                try:
                    plan = self.planner_fn(
                        request,
                        pdf_text,
                        model_config,
                        artifacts_dir=job_dir,
                    )
                    break
                except IntegrationFailure as _planning_exc:
                    (job_dir / f"error_planning_attempt_{_attempt}.log").write_text(
                        f"technical: {_planning_exc.technical_message}\n\n{traceback.format_exc()}",
                        encoding="utf-8",
                    )
                    if not _planning_exc.retryable or _attempt >= _MAX_PLANNING_ATTEMPTS:
                        raise
                    self._update_job(
                        job_id,
                        progress_message=(
                            f"OpenAI respondeu parcialmente (tentativa {_attempt}/{_MAX_PLANNING_ATTEMPTS}). "
                            "Tentando novamente..."
                        ),
                    )

            (job_dir / "plano_web.json").write_text(
                plan.model_dump_json(indent=2),
                encoding="utf-8",
            )
            self._update_job(
                job_id,
                title=plan.title,
                enhanced_brief=plan.enhanced_brief_pt,
                progress_message="Plano aprovado; iniciando renderização...",
            )

            def report_progress(step: str, message: str) -> None:
                nonlocal current_stage
                current_stage = step
                self._update_job(
                    job_id,
                    status=step,
                    step=step,
                    progress_message=message,
                )

            # Pass reference image paths and logo overlay preference
            render_result = self.renderer_fn(
                job_dir=job_dir,
                request=request,
                plan=plan,
                model_config=model_config,
                progress_cb=report_progress,
                ref_embalagem_path=metadata.get("ref_embalagem_path"),
                ref_logo_path=metadata.get("ref_logo_path"),
                ref_cores_path=metadata.get("ref_cores_path"),
                apply_logo_overlay=metadata.get("apply_logo_overlay", True),
            )
            warnings.extend(render_result.get("warnings", []))

            self._update_job(
                job_id,
                status="completed",
                step="completed",
                progress_message="Vídeo final pronto para preview e download.",
                warnings=warnings,
                final_video_path=render_result["final_video_path"],
                preview_url=f"/api/jobs/{job_id}/download",
                download_url=f"/api/jobs/{job_id}/download",
                error_message=None,
                failed_stage=None,
                failed_service=None,
                failure_code=None,
                retryable=None,
                user_message=None,
                auth_confirmed=None,
                submit_confirmed=None,
                render_confirmed=None,
                failure_reason=None,
            )
        except IntegrationFailure as failure:
            (job_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
            failure_fields = failure.to_status_fields()
            self._update_job(
                job_id,
                status="failed",
                step="failed",
                progress_message=failure.user_message,
                warnings=warnings,
                **failure_fields,
            )
        except Exception as exc:
            (job_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
            failure = build_generic_failure(stage=current_stage, exc=exc)
            self._update_job(
                job_id,
                status="failed",
                step="failed",
                progress_message=failure.user_message,
                warnings=warnings,
                **failure.to_status_fields(),
            )

    def _job_dir(self, job_id: str) -> Path:
        job_dir = self.jobs_dir / job_id
        if not job_dir.exists():
            raise FileNotFoundError(f"Job não encontrado: {job_id}")
        return job_dir

    def _metadata_path(self, job_dir: Path) -> Path:
        return job_dir / "metadata.json"

    def _read_metadata(self, job_dir: Path) -> dict[str, object]:
        return json.loads(self._metadata_path(job_dir).read_text(encoding="utf-8"))

    def _write_metadata(self, job_dir: Path, metadata: dict[str, object]) -> None:
        metadata["updated_at"] = datetime.utcnow().isoformat()
        target = self._metadata_path(job_dir)
        temp_path = target.with_suffix(".tmp")
        with self._lock:
            temp_path.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            temp_path.replace(target)

    def _update_job(self, job_id: str, **changes: object) -> None:
        job_dir = self._job_dir(job_id)
        metadata = self._read_metadata(job_dir)
        metadata.update(changes)
        self._write_metadata(job_dir, metadata)
