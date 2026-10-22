"""Shared structured failures for external integrations."""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx


@dataclass
class IntegrationFailure(Exception):
    """Structured failure that can be surfaced to the web UI and metadata."""

    service: str
    stage: str
    code: str
    user_message: str
    technical_message: str | None = None
    retryable: bool = False
    auth_confirmed: bool | None = None
    submit_confirmed: bool | None = None
    render_confirmed: bool | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.technical_message or self.user_message)

    def to_status_fields(self) -> dict[str, object]:
        return {
            "failed_stage": self.stage,
            "failed_service": self.service,
            "failure_code": self.code,
            "retryable": self.retryable,
            "user_message": self.user_message,
            "error_message": self.technical_message or self.user_message,
            "auth_confirmed": self.auth_confirmed,
            "submit_confirmed": self.submit_confirmed,
            "render_confirmed": self.render_confirmed,
            "failure_reason": self.reason,
        }


def build_generic_failure(*, stage: str, exc: Exception) -> IntegrationFailure:
    """Fallback wrapper for unexpected exceptions."""

    message = str(exc).strip() or exc.__class__.__name__
    return IntegrationFailure(
        service="unknown",
        stage=stage,
        code="unexpected_error",
        user_message=f"Falha inesperada durante {stage}. Consulte o log técnico para detalhes.",
        technical_message=message,
        retryable=False,
    )


HIGGSFIELD_SERVICE = "higgsfield"
HTTP_STATUS_PATTERN = re.compile(r"\bHTTP (\d{3})\b")
AUTH_STATUS_CODES = frozenset({401})
INSUFFICIENT_CREDITS_STATUS_CODES = frozenset({402, 403})
MODEL_BLOCKED_STATUS_CODE = 423
NOT_FOUND_STATUS_CODE = 404
INVALID_ARGUMENTS_STATUS_CODES = frozenset({400, 422})
RATE_LIMIT_STATUS_CODE = 429
SERVER_ERROR_MIN_STATUS_CODE = 500
CREDIT_MARKERS = ("credit", "saldo", "balance")
MODEL_BLOCKED_MARKERS = ("model_blocked", "model blocked")
NETWORK_MARKERS = ("connection", "10061", "network", "timeout", "timed out")


def _higgsfield_failure(
    *,
    stage: str,
    code: str,
    user_message: str,
    technical_message: str,
    retryable: bool,
    auth_confirmed: bool | None,
    submit_confirmed: bool,
) -> IntegrationFailure:
    return IntegrationFailure(
        service=HIGGSFIELD_SERVICE,
        stage=stage,
        code=code,
        user_message=user_message,
        technical_message=technical_message,
        retryable=retryable,
        auth_confirmed=auth_confirmed,
        submit_confirmed=submit_confirmed,
        render_confirmed=False,
        reason=code,
    )


def _http_status_code(exc: Exception, message: str) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    for candidate in (exc, exc.__cause__):
        if isinstance(candidate, httpx.HTTPStatusError):
            return candidate.response.status_code
    match = HTTP_STATUS_PATTERN.search(message)
    return int(match.group(1)) if match else None


def _is_network_failure(exc: Exception, lowered: str) -> bool:
    if isinstance(exc, (httpx.TransportError, OSError)):
        return True
    return any(marker in lowered for marker in NETWORK_MARKERS)


def classify_higgsfield_exception(exc: Exception, *, stage: str = "generating") -> IntegrationFailure:
    """Map Higgsfield failures to a structured contract."""

    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    status_code = _http_status_code(exc, message)

    if status_code in INSUFFICIENT_CREDITS_STATUS_CODES or any(marker in lowered for marker in CREDIT_MARKERS):
        return _higgsfield_failure(
            stage=stage,
            code="insufficient_credits",
            user_message="A conexão com a Higgsfield foi confirmada, mas a geração não pode prosseguir sem saldo.",
            technical_message=message,
            retryable=False,
            auth_confirmed=True,
            submit_confirmed=True,
        )

    if status_code in AUTH_STATUS_CODES or (
        status_code is None and ("unauthorized" in lowered or "forbidden" in lowered)
    ):
        return _higgsfield_failure(
            stage=stage,
            code="auth_invalid",
            user_message="Falha de autenticação na Higgsfield. Verifique as credenciais configuradas.",
            technical_message=message,
            retryable=False,
            auth_confirmed=False,
            submit_confirmed=False,
        )

    if status_code == MODEL_BLOCKED_STATUS_CODE or any(marker in lowered for marker in MODEL_BLOCKED_MARKERS):
        return _higgsfield_failure(
            stage=stage,
            code="model_blocked",
            user_message=(
                "A Higgsfield bloqueou a geração neste modelo. Isso costuma ocorrer quando o prompt "
                "ou a imagem de referência contém marca, logo ou produto de marca, ou quando o "
                "modelo está temporariamente bloqueado. Ajuste o prompt ou a referência, ou tente outro modelo."
            ),
            technical_message=message,
            retryable=False,
            auth_confirmed=True,
            submit_confirmed=True,
        )

    if status_code == NOT_FOUND_STATUS_CODE or "model not found" in lowered or (
        "model" in lowered and "not found" in lowered
    ):
        return _higgsfield_failure(
            stage=stage,
            code="model_not_found",
            user_message="A Higgsfield respondeu, mas o modelo selecionado não foi encontrado para esta conta.",
            technical_message=message,
            retryable=False,
            auth_confirmed=True,
            submit_confirmed=True,
        )

    if status_code in INVALID_ARGUMENTS_STATUS_CODES:
        return _higgsfield_failure(
            stage=stage,
            code="invalid_arguments",
            user_message="A Higgsfield rejeitou os parâmetros enviados para o modelo selecionado.",
            technical_message=message,
            retryable=False,
            auth_confirmed=True,
            submit_confirmed=False,
        )

    if status_code == RATE_LIMIT_STATUS_CODE:
        return _higgsfield_failure(
            stage=stage,
            code="rate_limited",
            user_message="A Higgsfield limitou temporariamente as requisições. Tente novamente em instantes.",
            technical_message=message,
            retryable=True,
            auth_confirmed=True,
            submit_confirmed=False,
        )

    if status_code is not None and status_code >= SERVER_ERROR_MIN_STATUS_CODE:
        return _higgsfield_failure(
            stage=stage,
            code="provider_unavailable",
            user_message="A Higgsfield está instável no momento. Tente novamente em instantes.",
            technical_message=message,
            retryable=True,
            auth_confirmed=None,
            submit_confirmed=False,
        )

    if _is_network_failure(exc, lowered):
        return _higgsfield_failure(
            stage=stage,
            code="network_error",
            user_message="Falha ao conectar na Higgsfield durante a geração. Verifique a conectividade externa.",
            technical_message=message,
            retryable=True,
            auth_confirmed=None,
            submit_confirmed=False,
        )

    if "output url" in lowered or "sem url" in lowered:
        return _higgsfield_failure(
            stage=stage,
            code="missing_output_url",
            user_message="A Higgsfield concluiu a requisição, mas não devolveu uma URL válida de saída.",
            technical_message=message,
            retryable=True,
            auth_confirmed=True,
            submit_confirmed=True,
        )

    return _higgsfield_failure(
        stage=stage,
        code="generation_failed",
        user_message="A Higgsfield não conseguiu concluir a geração do vídeo.",
        technical_message=message,
        retryable=True,
        auth_confirmed=True,
        submit_confirmed=True,
    )
