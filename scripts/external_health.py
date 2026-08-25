"""Structured external health checks for the web UI."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.config import OUTPUT_DIR
from scripts.health_check import (
    check_elevenlabs,
    check_ffmpeg,
    check_higgsfield,
    check_openai,
)
from scripts.integration_errors import classify_higgsfield_exception
from webapp.model_registry import get_model_config
from webapp.schemas import ExternalHealthResponse, ExternalServiceHealth

logger = logging.getLogger(__name__)

EXTERNAL_HEALTH_CACHE_SECONDS = max(
    0,
    int(os.getenv("JW_EXTERNAL_HEALTH_CACHE_SECONDS", "300")),
)
HIGGSFIELD_CREDIT_BLOCK_SECONDS = max(
    0,
    int(os.getenv("JW_HIGGSFIELD_CREDIT_BLOCK_SECONDS", "1800")),
)

_probe_cache: tuple[
    float,
    tuple[tuple[bool, str], tuple[bool, str], tuple[bool, str], tuple[bool, str]],
] | None = None
_probe_cache_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metadata_timestamp(metadata: dict[str, object], path: Path) -> float:
    updated_at = metadata.get("updated_at")
    if isinstance(updated_at, str):
        try:
            parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            logger.warning("Invalid job timestamp in %s", path)
    return path.stat().st_mtime


def _is_higgsfield_job(metadata: dict[str, object]) -> bool:
    request = metadata.get("request")
    if not isinstance(request, dict):
        return metadata.get("failed_service") == "higgsfield"

    model_key = request.get("video_model")
    if not isinstance(model_key, str):
        return metadata.get("failed_service") == "higgsfield"

    try:
        return not get_model_config(model_key).application.startswith("openai:")
    except ValueError:
        return metadata.get("failed_service") == "higgsfield"


def _latest_higgsfield_credit_failure(
    jobs_dir: Path,
    *,
    now_timestamp: float | None = None,
    block_seconds: int = HIGGSFIELD_CREDIT_BLOCK_SECONDS,
) -> dict[str, object] | None:
    latest_event: tuple[float, dict[str, object]] | None = None
    if not jobs_dir.exists():
        return None

    for metadata_path in jobs_dir.glob("*/metadata.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring unreadable job metadata %s: %s", metadata_path, exc)
            continue

        if not isinstance(metadata, dict) or not _is_higgsfield_job(metadata):
            continue

        is_credit_failure = (
            metadata.get("failed_service") == "higgsfield"
            and metadata.get("failure_code") == "insufficient_credits"
        )
        if not is_credit_failure and metadata.get("status") != "completed":
            continue

        event = (_metadata_timestamp(metadata, metadata_path), metadata)
        if latest_event is None or event[0] > latest_event[0]:
            latest_event = event

    if latest_event is None:
        return None

    event_timestamp, metadata = latest_event
    if metadata.get("failure_code") == "insufficient_credits":
        if block_seconds <= 0:
            return None
        current_timestamp = now_timestamp or datetime.now(timezone.utc).timestamp()
        if event_timestamp < current_timestamp - block_seconds:
            return None
        return metadata
    return None


def _run_provider_probes() -> tuple[
    tuple[bool, str],
    tuple[bool, str],
    tuple[bool, str],
    tuple[bool, str],
]:
    return (
        check_ffmpeg(),
        check_openai(),
        check_higgsfield(),
        check_elevenlabs(),
    )


def _provider_probes(*, use_cache: bool) -> tuple[
    tuple[bool, str],
    tuple[bool, str],
    tuple[bool, str],
    tuple[bool, str],
]:
    global _probe_cache

    if not use_cache or EXTERNAL_HEALTH_CACHE_SECONDS <= 0:
        return _run_provider_probes()

    now = time.monotonic()
    with _probe_cache_lock:
        if _probe_cache and now - _probe_cache[0] < EXTERNAL_HEALTH_CACHE_SECONDS:
            return _probe_cache[1]
        probes = _run_provider_probes()
        _probe_cache = (now, probes)
        return probes


def probe_external_health(
    *,
    startup_mode: str | None = None,
    external_connectivity_checked: bool | None = None,
    jobs_dir: Path | None = None,
    use_cached_probes: bool = False,
) -> ExternalHealthResponse:
    """Return structured health information for the UI."""

    (
        (ffmpeg_ok, ffmpeg_message),
        (openai_ok, openai_message),
        (higgs_ok, higgs_message),
        (eleven_ok, eleven_message),
    ) = _provider_probes(use_cache=use_cached_probes)

    higgs_reason = None
    higgs_auth_confirmed = None
    if higgs_ok:
        higgs_auth_confirmed = False
        higgs_reason = "credentials_configured"
    else:
        logger.warning("Higgsfield health check failed: %s", higgs_message)
        raw_message = higgs_message.split("Erro:", 1)[1].strip() if "Erro:" in higgs_message else higgs_message
        failure = classify_higgsfield_exception(RuntimeError(raw_message), stage="healthcheck")
        higgs_auth_confirmed = failure.auth_confirmed
        higgs_reason = failure.reason
        higgs_message = "Higgsfield indisponivel; consulte os logs do servidor."

    if not openai_ok:
        logger.warning("OpenAI health check failed: %s", openai_message)
        openai_message = "OpenAI indisponivel; consulte os logs do servidor."
    if not eleven_ok:
        logger.warning("ElevenLabs health check failed: %s", eleven_message)
        eleven_message = "ElevenLabs indisponivel; consulte os logs do servidor."

    credit_failure = _latest_higgsfield_credit_failure(
        jobs_dir or OUTPUT_DIR / "web_jobs"
    )
    if higgs_ok and credit_failure:
        higgs_ok = False
        higgs_message = "A Higgsfield confirmou autenticação, mas não possui créditos disponíveis."
        higgs_auth_confirmed = True
        higgs_reason = "insufficient_credits"

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
            submit_confirmed=True if credit_failure else False,
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
