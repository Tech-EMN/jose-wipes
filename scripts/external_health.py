"""Structured external health checks for the web UI."""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.health_check import (
    check_elevenlabs,
    check_ffmpeg,
    check_higgsfield,
    check_openai,
)
from scripts.integration_errors import classify_higgsfield_exception
from webapp.schemas import ExternalHealthResponse, ExternalServiceHealth


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def probe_external_health(
    *,
    startup_mode: str | None = None,
    external_connectivity_checked: bool | None = None,
) -> ExternalHealthResponse:
    """Return structured health information for the UI."""

    ffmpeg_ok, ffmpeg_message = check_ffmpeg()
    openai_ok, openai_message = check_openai()
    higgs_ok, higgs_message = check_higgsfield()
    eleven_ok, eleven_message = check_elevenlabs()

    higgs_reason = None
    higgs_auth_confirmed = None
    if higgs_ok:
        higgs_auth_confirmed = True
        higgs_reason = "auth_confirmed_only"
    else:
        raw_message = higgs_message.split("Erro:", 1)[1].strip() if "Erro:" in higgs_message else higgs_message
        failure = classify_higgsfield_exception(RuntimeError(raw_message), stage="healthcheck")
        higgs_auth_confirmed = failure.auth_confirmed
        higgs_reason = failure.reason

    services = {
        "ffmpeg": ExternalServiceHealth(
            ok=ffmpeg_ok,
            status="ok" if ffmpeg_ok else "error",
            message=ffmpeg_message,
        ),
        "openai": ExternalServiceHealth(
            ok=openai_ok,
            status="ok" if openai_ok else "error",
            message=openai_message,
        ),
        "higgsfield_auth": ExternalServiceHealth(
            ok=higgs_ok,
            status="ok" if higgs_ok else "error",
            message=higgs_message,
            auth_confirmed=higgs_auth_confirmed,
            submit_confirmed=False,
            render_confirmed=False,
            reason=higgs_reason,
        ),
        "elevenlabs": ExternalServiceHealth(
            ok=eleven_ok,
            status="ok" if eleven_ok else "error",
            message=eleven_message,
        ),
    }

    ready_for_submit = all(
        services[name].ok
        for name in ("ffmpeg", "openai", "higgsfield_auth", "elevenlabs")
    )
    return ExternalHealthResponse(
        ready_for_submit=ready_for_submit,
        checked_at=_now_iso(),
        startup_mode=startup_mode,
        external_connectivity_checked=external_connectivity_checked,
        services=services,
    )
