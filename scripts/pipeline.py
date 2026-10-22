"""Linha de comando do Studio: roda um vídeo pelo mesmo caminho da web.

Moderação, planner (OpenAI) e render (``jose_wipes.rendering.pipeline_service``) são os
mesmos usados em produção; o job fica em ``output/web_jobs`` como os da web.

Exemplos:
    python scripts/pipeline.py "Vídeo de 30s estilo grupo de apoio"
    python scripts/pipeline.py --arquivo briefing.txt --duracao 60 --modelo kling_3_0
    python scripts/pipeline.py --pdf roteiro.pdf "Siga o roteiro anexo"
    python scripts/pipeline.py --plano output/web_jobs/<job_id>/plano_web.json
    python scripts/pipeline.py --retomar <job_id>
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jose_wipes.jobs.job_manager import JobManager, ProgressListener
from jose_wipes.moderation import moderate_prompt_sync
from jose_wipes.result import Err
from jose_wipes.schemas import (
    CreateJobRequest,
    DurationLiteral,
    JobStatusResponse,
    OrientationLiteral,
    PlannerOutput,
    ResolutionLiteral,
    VideoModelLiteral,
)

DEFAULT_RESOLUTION = "1080p"
DEFAULT_ORIENTATION = "vertical"
DEFAULT_DURATION_SECONDS = 30
DEFAULT_VIDEO_MODEL = "seedance_1_5_pro"
COMPLETED_STATUS = "completed"
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


@dataclass(frozen=True)
class PipelineRun:
    """Outcome of one run; ``blocked_reason`` is set when moderation refuses the prompt
    and ``rejected_reason`` when a job cannot be resumed."""

    job_id: str | None
    status: JobStatusResponse | None
    final_video_path: Path | None
    blocked_reason: str | None = None
    rejected_reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return (
            self.status is not None
            and self.status.status == COMPLETED_STATUS
            and self.final_video_path is not None
        )


def run_pipeline(
    request: CreateJobRequest,
    *,
    plan: PlannerOutput | None = None,
    script_pdf: Path | None = None,
    apply_logo_overlay: bool = True,
    use_product_reference: bool = True,
    jobs_dir: Path | None = None,
    on_progress: ProgressListener | None = None,
) -> PipelineRun:
    """Create a job like the web form does and process it synchronously."""

    moderation = moderate_prompt_sync(request.prompt)
    if not moderation.allowed:
        return PipelineRun(
            job_id=None,
            status=None,
            final_video_path=None,
            blocked_reason=moderation.reason or "Conteúdo bloqueado pela moderação.",
        )

    manager = JobManager(
        jobs_dir=jobs_dir,
        planner_fn=_fixed_planner(plan) if plan else None,
        progress_listener=on_progress,
    )
    metadata = manager.create_job(
        request,
        script_pdf_bytes=script_pdf.read_bytes() if script_pdf else None,
        script_pdf_name=script_pdf.name if script_pdf else None,
        apply_logo_overlay=apply_logo_overlay,
        use_product_reference=use_product_reference,
    )
    job_id = str(metadata["job_id"])
    status = manager.run_now(job_id)
    return PipelineRun(
        job_id=job_id,
        status=status,
        final_video_path=manager.get_download_path(job_id),
    )


def resume_pipeline(
    job_id: str,
    *,
    jobs_dir: Path | None = None,
    on_progress: ProgressListener | None = None,
) -> PipelineRun:
    """Re-run a failed job from the render stage that did not finish."""

    manager = JobManager(jobs_dir=jobs_dir, progress_listener=on_progress)
    retried = manager.retry_job(job_id)
    if isinstance(retried, Err):
        return PipelineRun(
            job_id=job_id,
            status=None,
            final_video_path=None,
            rejected_reason=retried.failure.user_message,
        )
    status = manager.run_now(job_id)
    return PipelineRun(
        job_id=job_id,
        status=status,
        final_video_path=manager.get_download_path(job_id),
    )


def _fixed_planner(plan: PlannerOutput):
    def planner(request, pdf_text, model_config, *, artifacts_dir=None) -> PlannerOutput:
        return plan

    return planner


def print_progress(job_id: str, metadata: dict[str, object]) -> None:
    print(f"  [{metadata.get('status')}] {metadata.get('progress_message')}", flush=True)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="José Wipes — gera um vídeo pelo mesmo pipeline da web.",
    )
    parser.add_argument("briefing", nargs="?", help="Briefing em texto")
    parser.add_argument("--arquivo", type=Path, help="Ler o briefing de um arquivo de texto")
    parser.add_argument("--pdf", type=Path, help="Roteiro em PDF, como o upload da web")
    parser.add_argument("--plano", type=Path, help="Reusar um plano_web.json e pular o planner")
    parser.add_argument("--retomar", metavar="JOB_ID", help="Retomar um job que falhou a partir da etapa que parou")
    parser.add_argument("--modelo", choices=get_args(VideoModelLiteral), default=DEFAULT_VIDEO_MODEL)
    parser.add_argument("--resolucao", choices=get_args(ResolutionLiteral), default=DEFAULT_RESOLUTION)
    parser.add_argument("--orientacao", choices=get_args(OrientationLiteral), default=DEFAULT_ORIENTATION)
    parser.add_argument(
        "--duracao",
        type=int,
        choices=get_args(DurationLiteral),
        default=DEFAULT_DURATION_SECONDS,
    )
    parser.add_argument("--sem-logo", action="store_true", help="Não aplicar o logo sobre o vídeo")
    parser.add_argument(
        "--sem-referencia-produto",
        action="store_true",
        help="Não usar a foto da embalagem como referência nas cenas de produto",
    )
    return parser.parse_args(argv)


def _resolve_prompt(args: argparse.Namespace, plan: PlannerOutput | None) -> str | None:
    if args.arquivo:
        return args.arquivo.read_text(encoding="utf-8")
    if args.briefing:
        return args.briefing
    if plan:
        return plan.enhanced_brief_pt
    return None


def _print_summary(run: PipelineRun) -> None:
    print("\n" + "=" * 60)
    if run.blocked_reason:
        print(f"  Bloqueado pela moderação: {run.blocked_reason}")
        return
    if run.rejected_reason:
        print(f"  Não foi possível retomar o job {run.job_id}: {run.rejected_reason}")
        return
    status = run.status
    print(f"  Job: {run.job_id}")
    print(f"  Status: {status.status if status else '?'}")
    if run.final_video_path:
        print(f"  Vídeo: {run.final_video_path}")
    if status and status.drive_url:
        print(f"  Google Drive: {status.drive_url}")
    if status and status.warnings:
        print(f"  Avisos: {'; '.join(status.warnings)}")
    if status and not run.succeeded:
        print(f"  Falha em {status.failed_stage} ({status.failure_code}): {status.user_message}")
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parse_args(argv)

    if args.retomar:
        try:
            run = resume_pipeline(args.retomar, on_progress=print_progress)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE
        _print_summary(run)
        return EXIT_SUCCESS if run.succeeded else EXIT_FAILURE

    plan = PlannerOutput.model_validate_json(args.plano.read_text(encoding="utf-8")) if args.plano else None
    prompt = _resolve_prompt(args, plan)
    if not prompt:
        print("Informe um briefing, --arquivo ou --plano.", file=sys.stderr)
        return EXIT_USAGE

    request = CreateJobRequest.model_validate(
        {
            "resolution": args.resolucao,
            "orientation": args.orientacao,
            "duration_seconds": args.duracao,
            "prompt": prompt,
            "video_model": args.modelo,
        }
    )
    run = run_pipeline(
        request,
        plan=plan,
        script_pdf=args.pdf,
        apply_logo_overlay=not args.sem_logo,
        use_product_reference=not args.sem_referencia_produto,
        on_progress=print_progress,
    )
    _print_summary(run)
    return EXIT_SUCCESS if run.succeeded else EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())
