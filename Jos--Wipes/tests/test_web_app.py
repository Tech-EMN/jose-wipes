"""Valida a app FastAPI do web studio com job manager mockado."""

import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    print("=" * 50)
    print("TESTE: Web App")
    print("=" * 50)

    try:
        from fastapi.testclient import TestClient
    except ImportError:
        print("  x fastapi nao instalado. Instale as dependencias web primeiro.")
        return 1

    from webapp.main import app
    import webapp.main as main_module
    from webapp.schemas import ExternalHealthResponse, ExternalServiceHealth, JobStatusResponse

    temp_dir = Path(__file__).parent.parent / "output" / "test_web_app"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        video_path = temp_dir / "preview.mp4"
        video_path.write_bytes(b"fake video")

        class FakeManager:
            def start(self):
                return None

            def stop(self):
                return None

            def create_job(self, request_model, script_pdf_bytes=None, script_pdf_name=None):
                self.request_model = request_model
                self.script_pdf_name = script_pdf_name
                self.script_pdf_bytes = script_pdf_bytes
                return {"job_id": "job123"}

            def get_job_status(self, job_id):
                return JobStatusResponse(
                    job_id=job_id,
                    status="completed",
                    step="completed",
                    progress_message="ok",
                    warnings=["warning"],
                    title="Teste",
                    enhanced_brief="Briefing refinado",
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

            def get_download_path(self, job_id):
                return video_path

        main_module.job_manager = FakeManager()
        main_module.get_web_server_status = lambda **kwargs: {
            "startup_mode": "runner",
            "external_connectivity_checked": True,
        }
        main_module.mark_external_connectivity_checked = lambda **kwargs: {}
        main_module.probe_external_health = lambda **kwargs: ExternalHealthResponse(
            ready_for_submit=True,
            checked_at="2026-04-09T00:00:00Z",
            startup_mode="runner",
            external_connectivity_checked=True,
            services={
                "ffmpeg": ExternalServiceHealth(ok=True, status="ok", message="ok"),
                "openai": ExternalServiceHealth(ok=True, status="ok", message="ok"),
                "higgsfield_auth": ExternalServiceHealth(
                    ok=True,
                    status="ok",
                    message="ok",
                    auth_confirmed=True,
                    submit_confirmed=False,
                    render_confirmed=False,
                    reason="auth_confirmed_only",
                ),
                "elevenlabs": ExternalServiceHealth(ok=True, status="ok", message="ok"),
            },
        )

        with TestClient(app) as client:
            response = client.get("/")
            if response.status_code != 200:
                print(f"  x GET / falhou: {response.status_code}")
                return 1

            response = client.get("/api/health/external")
            if response.status_code != 200:
                print(f"  x GET /api/health/external falhou: {response.status_code}")
                return 1
            payload = response.json()
            if not payload.get("ready_for_submit"):
                print(f"  x Health externo deveria estar pronto: {payload}")
                return 1
            if "openai" not in payload.get("services", {}):
                print(f"  x Health externo sem servicos esperados: {payload}")
                return 1

            response = client.post(
                "/api/jobs",
                data={
                    "resolution": "1080p",
                    "orientation": "vertical",
                    "duration_seconds": "30",
                    "prompt": "Prompt de teste",
                    "video_model": "kling_3_0",
                },
            )
            if response.status_code != 200:
                print(f"  x POST /api/jobs falhou: {response.text}")
                return 1

            response = client.post(
                "/api/jobs",
                data={
                    "resolution": "1080p",
                    "orientation": "vertical",
                    "duration_seconds": "30",
                    "prompt": "Prompt de teste",
                    "video_model": "kling_3_0",
                },
                files={"script_pdf": ("roteiro.txt", b"nao", "text/plain")},
            )
            if response.status_code != 400:
                print(f"  x Arquivo invalido deveria falhar com 400: {response.status_code}")
                return 1

            response = client.get("/api/jobs/job123")
            if response.status_code != 200:
                print(f"  x GET /api/jobs/job123 falhou: {response.status_code}")
                return 1

            response = client.get("/api/jobs/job123/download")
            if response.status_code != 200:
                print(f"  x Download falhou: {response.status_code}")
                return 1

        print("  + App responde formulario, health externo, status e download")
        print("-" * 50)
        print("  + TESTE WEB APP: PASSOU")
        return 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
