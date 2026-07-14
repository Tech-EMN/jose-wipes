"""FastAPI app for the José Wipes Web Video Studio V2."""

from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from scripts.config import PROJECT_ROOT
from scripts.external_health import probe_external_health
from scripts.web_server import get_web_server_status, mark_external_connectivity_checked
from webapp.auth import AuthMiddleware
from webapp.job_manager import JobManager
from webapp.moderation import moderate_prompt_sync
from webapp.rate_limit import RateLimitMiddleware
from webapp.pdf_utils import MAX_PDF_BYTES
from webapp.schemas import CreateJobRequest

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB per image

app = FastAPI(title="José Wipes Web Video Studio", version="2.0.0")
app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimitMiddleware)
job_manager = JobManager()

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")
app.mount("/assets/logo", StaticFiles(directory=str(PROJECT_ROOT / "assets" / "logo")), name="logo")
app.mount(
    "/assets/referencias",
    StaticFiles(directory=str(PROJECT_ROOT / "assets" / "referencias")),
    name="referencias",
)


@app.on_event("startup")
def startup_event() -> None:
    """Start the background worker only when running in single-container mode.

    Set JW_SKIP_WORKER=true in the web container when using separate
    web + worker services (production docker-compose).
    """
    import os
    if os.getenv("JW_SKIP_WORKER", "").strip().lower() in {"true", "1", "yes"}:
        import logging
        _log = logging.getLogger("webapp.main")
        _log.info("JW_SKIP_WORKER=true — web server running without background worker")
        return
    job_manager.start()


@app.on_event("shutdown")
def shutdown_event() -> None:
    """Stop the job worker cleanly."""

    job_manager.stop()


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Render the main internal tool page."""

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "max_pdf_mb": MAX_PDF_BYTES // (1024 * 1024),
        },
    )


@app.get("/api/health/external")
def get_external_health() -> JSONResponse:
    """Return structured external connectivity for the UI."""

    runtime_status = get_web_server_status(check_http=False)
    payload = probe_external_health(
        startup_mode=runtime_status.get("startup_mode"),
        external_connectivity_checked=runtime_status.get("external_connectivity_checked"),
    )
    updated_runtime = mark_external_connectivity_checked(ok=payload.ready_for_submit)
    if updated_runtime:
        payload.external_connectivity_checked = updated_runtime.get(
            "external_connectivity_checked"
        )
    return JSONResponse(payload.model_dump())


async def _read_upload_image(
    upload: UploadFile | None,
    label: str,
) -> tuple[bytes | None, str | None]:
    """Read and validate an uploaded image file."""

    if not upload or not upload.filename:
        return None, None

    content_type = upload.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=f"O arquivo de {label} precisa ser uma imagem (recebido: {content_type}).",
        )

    data = await upload.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"A imagem de {label} excede o limite de {MAX_IMAGE_BYTES // (1024 * 1024)} MB.",
        )

    return data, upload.filename


@app.post("/api/jobs")
async def create_job(
    resolution: str = Form(...),
    orientation: str = Form(...),
    duration_seconds: int = Form(...),
    prompt: str = Form(...),
    video_model: str = Form(...),
    apply_logo_overlay: str = Form(default="true"),
    script_pdf: UploadFile | None = File(default=None),
    ref_embalagem: UploadFile | None = File(default=None),
    ref_logo: UploadFile | None = File(default=None),
    ref_cores: UploadFile | None = File(default=None),
) -> JSONResponse:
    """Create a background job from the submitted web form."""

    # Content safety check before any external API call
    moderation = moderate_prompt_sync(prompt)
    if not moderation.allowed:
        raise HTTPException(
            status_code=400,
            detail=moderation.reason or "Conteúdo bloqueado pela moderação.",
        )

    try:
        request_model = CreateJobRequest.model_validate(
            {
                "resolution": resolution,
                "orientation": orientation,
                "duration_seconds": duration_seconds,
                "prompt": prompt,
                "video_model": video_model,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    pdf_bytes = None
    pdf_name = None
    if script_pdf and script_pdf.filename:
        filename = script_pdf.filename.lower()
        if not filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

        pdf_bytes = await script_pdf.read()
        if len(pdf_bytes) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"O PDF excede o limite de {MAX_PDF_BYTES // (1024 * 1024)} MB.",
            )
        pdf_name = script_pdf.filename

    # Read reference images
    embalagem_data, embalagem_name = await _read_upload_image(ref_embalagem, "embalagem")
    logo_data, logo_name = await _read_upload_image(ref_logo, "logo")
    cores_data, cores_name = await _read_upload_image(ref_cores, "cores da marca")

    metadata = job_manager.create_job(
        request_model,
        script_pdf_bytes=pdf_bytes,
        script_pdf_name=pdf_name,
        ref_embalagem_bytes=embalagem_data,
        ref_embalagem_name=embalagem_name,
        ref_logo_bytes=logo_data,
        ref_logo_name=logo_name,
        ref_cores_bytes=cores_data,
        ref_cores_name=cores_name,
        apply_logo_overlay=apply_logo_overlay.lower() in {"true", "1", "yes", "sim"},
    )
    status = job_manager.get_job_status(metadata["job_id"])

    return JSONResponse(
        {
            "job_id": status.job_id,
            "status": status.status,
            "status_url": f"/api/jobs/{status.job_id}",
            "download_url": status.download_url,
        }
    )


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> JSONResponse:
    """Return the current status of a job."""

    try:
        status = job_manager.get_job_status(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return JSONResponse(status.model_dump())


@app.get("/api/jobs/{job_id}/download")
def download_job_video(job_id: str) -> FileResponse:
    """Stream the finished video once a job is completed."""

    try:
        video_path = job_manager.get_download_path(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not video_path:
        raise HTTPException(status_code=409, detail="O vídeo ainda não está pronto para download.")

    return FileResponse(path=video_path, media_type="video/mp4", filename=video_path.name)
