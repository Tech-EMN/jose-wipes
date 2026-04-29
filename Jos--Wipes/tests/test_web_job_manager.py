"""Valida o fluxo assincrono do JobManager com planner/render mockados."""

import shutil
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.integration_errors import IntegrationFailure
from webapp.job_manager import JobManager
from webapp.schemas import CreateJobRequest, PlannerOutput, PlannerShot, ProductOverlayConfig


def fake_planner(request, pdf_text, model_config, *, artifacts_dir=None):
    return PlannerOutput(
        title="Teste Interno",
        enhanced_brief_pt="Briefing refinado para job manager.",
        global_style="Comercial rapido",
        final_cta_pt="CTA final",
        notes="",
        shots=[
            PlannerShot(
                shot_number=1,
                visual_prompt_en="Confident male hero in premium bathroom commercial lighting.",
                duration_seconds=5,
                narration_text_pt="Linha 1",
                voice_persona="narrador",
                overlay_text="Texto 1",
                product_overlay=ProductOverlayConfig(),
            ),
            PlannerShot(
                shot_number=2,
                visual_prompt_en="Product reveal in stylish bathroom with premium framing.",
                duration_seconds=5,
                narration_text_pt="Linha 2",
                voice_persona="narrador",
                overlay_text="CTA final",
                product_overlay=ProductOverlayConfig(ativo=True, posicao="centro_inferior"),
            ),
        ],
    )


def fake_renderer(*, job_dir, request, plan, model_config, progress_cb=None):
    if progress_cb:
        progress_cb("generating", "Gerando mock...")
        progress_cb("composing", "Compondo mock...")

    final_dir = Path(job_dir) / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_video = final_dir / "mock_video.mp4"
    final_video.write_bytes(b"fake video bytes")
    return {
        "final_video_path": str(final_video),
        "warnings": ["warning de teste"],
    }


def failing_planner(request, pdf_text, model_config, *, artifacts_dir=None):
    raise IntegrationFailure(
        service="openai",
        stage="planning",
        code="connection_error",
        user_message="Falha ao conectar na OpenAI durante o planejamento. Verifique conectividade externa ou o status da OpenAI.",
        technical_message="Connection error.",
        retryable=True,
    )


def invalid_payload_planner(request, pdf_text, model_config, *, artifacts_dir=None):
    raise IntegrationFailure(
        service="openai",
        stage="planning",
        code="invalid_planner_payload",
        user_message="A OpenAI retornou um plano invalido para o Web Studio. Revise o prompt ou tente novamente.",
        technical_message="1 validation error for PlannerOutput",
        retryable=True,
    )


def failing_renderer(*, job_dir, request, plan, model_config, progress_cb=None):
    if progress_cb:
        progress_cb("generating", "Gerando mock com falha...")

    raise IntegrationFailure(
        service="higgsfield",
        stage="generating",
        code="insufficient_credits",
        user_message="A conexao com a Higgsfield foi confirmada, mas a geracao nao pode prosseguir sem saldo.",
        technical_message="Insufficient credits",
        retryable=False,
        auth_confirmed=True,
        submit_confirmed=True,
        render_confirmed=False,
        reason="insufficient_credits",
    )


def wait_for_terminal_status(manager: JobManager, job_id: str, timeout_seconds: float = 5.0):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status = manager.get_job_status(job_id)
        if status.status in {"completed", "failed"}:
            return status
        time.sleep(0.1)
    return None


def main():
    print("=" * 50)
    print("TESTE: Web Job Manager")
    print("=" * 50)

    temp_dir = Path(__file__).parent.parent / "output" / "test_web_job_manager"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        request = CreateJobRequest(
            resolution="720p",
            orientation="horizontal",
            duration_seconds=10,
            prompt="Anuncio interno de teste.",
            video_model="kling_3_0",
        )

        manager = JobManager(
            jobs_dir=temp_dir / "success",
            planner_fn=fake_planner,
            renderer_fn=fake_renderer,
        )
        manager.start()
        job_id = manager.create_job(request)["job_id"]
        status = wait_for_terminal_status(manager, job_id)
        manager.stop()

        if status is None:
            print("  x Timeout aguardando conclusao do job")
            return 1
        if status.status != "completed":
            print(f"  x Job de sucesso falhou: {status.error_message}")
            return 1

        download_path = manager.get_download_path(job_id)
        if not download_path or not download_path.exists():
            print("  x Caminho de download nao foi salvo")
            return 1

        manager = JobManager(
            jobs_dir=temp_dir / "planning_failure",
            planner_fn=failing_planner,
            renderer_fn=fake_renderer,
        )
        manager.start()
        planning_job_id = manager.create_job(request)["job_id"]
        planning_status = wait_for_terminal_status(manager, planning_job_id)
        manager.stop()

        if planning_status is None:
            print("  x Timeout aguardando falha da OpenAI")
            return 1
        if planning_status.failed_service != "openai":
            print(f"  x Servico OpenAI nao foi classificado corretamente: {planning_status}")
            return 1
        if planning_status.failed_stage != "planning":
            print(f"  x Etapa OpenAI incorreta: {planning_status.failed_stage}")
            return 1
        if planning_status.failure_code != "connection_error":
            print(f"  x Codigo OpenAI incorreto: {planning_status.failure_code}")
            return 1

        manager = JobManager(
            jobs_dir=temp_dir / "planning_invalid_payload",
            planner_fn=invalid_payload_planner,
            renderer_fn=fake_renderer,
        )
        manager.start()
        invalid_job_id = manager.create_job(request)["job_id"]
        invalid_status = wait_for_terminal_status(manager, invalid_job_id)
        manager.stop()

        if invalid_status is None:
            print("  x Timeout aguardando falha de payload invalido")
            return 1
        if invalid_status.failed_service != "openai":
            print(f"  x Payload invalido deveria apontar para openai: {invalid_status}")
            return 1
        if invalid_status.failed_stage != "planning":
            print(f"  x Stage invalido para payload invalido: {invalid_status}")
            return 1
        if invalid_status.failure_code != "invalid_planner_payload":
            print(f"  x Codigo invalido para payload invalido: {invalid_status}")
            return 1

        manager = JobManager(
            jobs_dir=temp_dir / "higgsfield_failure",
            planner_fn=fake_planner,
            renderer_fn=failing_renderer,
        )
        manager.start()
        higgs_job_id = manager.create_job(request)["job_id"]
        higgs_status = wait_for_terminal_status(manager, higgs_job_id)
        manager.stop()

        if higgs_status is None:
            print("  x Timeout aguardando falha da Higgsfield")
            return 1
        if higgs_status.failed_service != "higgsfield":
            print(f"  x Servico Higgsfield nao foi classificado corretamente: {higgs_status}")
            return 1
        if higgs_status.failure_code != "insufficient_credits":
            print(f"  x Codigo Higgsfield incorreto: {higgs_status.failure_code}")
            return 1
        if higgs_status.auth_confirmed is not True:
            print(f"  x auth_confirmed deveria ser True: {higgs_status}")
            return 1
        if higgs_status.render_confirmed is not False:
            print(f"  x render_confirmed deveria ser False: {higgs_status}")
            return 1

        print("  + Job assincrono completa e salva video final")
        print("  + Falhas OpenAI e Higgsfield ficam estruturadas em metadata/status")
        print("-" * 50)
        print("  + TESTE WEB JOB MANAGER: PASSOU")
        return 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
