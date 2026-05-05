"""Shared structured failures for external integrations."""

from __future__ import annotations

from dataclasses import dataclass


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


def classify_higgsfield_exception(exc: Exception, *, stage: str = "generating") -> IntegrationFailure:
    """Map Higgsfield failures to a structured contract."""

    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()

    if "credit" in lowered or "saldo" in lowered or "insufficient" in lowered:
        return IntegrationFailure(
            service="higgsfield",
            stage=stage,
            code="insufficient_credits",
            user_message="A conexão com a Higgsfield foi confirmada, mas a geração não pode prosseguir sem saldo.",
            technical_message=message,
            retryable=False,
            auth_confirmed=True,
            submit_confirmed=True,
            render_confirmed=False,
            reason="insufficient_credits",
        )

    if "model not found" in lowered or ("model" in lowered and "not found" in lowered):
        return IntegrationFailure(
            service="higgsfield",
            stage=stage,
            code="model_not_found",
            user_message="A Higgsfield respondeu, mas o modelo selecionado não foi encontrado para esta conta.",
            technical_message=message,
            retryable=False,
            auth_confirmed=True,
            submit_confirmed=True,
            render_confirmed=False,
            reason="model_not_found",
        )

    if "401" in lowered or "403" in lowered or "unauthorized" in lowered or "forbidden" in lowered:
        return IntegrationFailure(
            service="higgsfield",
            stage=stage,
            code="auth_invalid",
            user_message="Falha de autenticação na Higgsfield. Verifique as credenciais configuradas.",
            technical_message=message,
            retryable=False,
            auth_confirmed=False,
            submit_confirmed=False,
            render_confirmed=False,
            reason="auth_invalid",
        )

    if "connection" in lowered or "10061" in lowered or "network" in lowered or "timeout" in lowered:
        return IntegrationFailure(
            service="higgsfield",
            stage=stage,
            code="network_error",
            user_message="Falha ao conectar na Higgsfield durante a geração. Verifique a conectividade externa.",
            technical_message=message,
            retryable=True,
            auth_confirmed=None,
            submit_confirmed=False,
            render_confirmed=False,
            reason="network_error",
        )

    if "output url" in lowered or "sem url" in lowered:
        return IntegrationFailure(
            service="higgsfield",
            stage=stage,
            code="missing_output_url",
            user_message="A Higgsfield concluiu a requisição, mas não devolveu uma URL válida de saída.",
            technical_message=message,
            retryable=True,
            auth_confirmed=True,
            submit_confirmed=True,
            render_confirmed=False,
            reason="missing_output_url",
        )

    return IntegrationFailure(
        service="higgsfield",
        stage=stage,
        code="generation_failed",
        user_message="A Higgsfield não conseguiu concluir a geração do vídeo.",
        technical_message=message,
        retryable=True,
        auth_confirmed=True,
        submit_confirmed=True,
        render_confirmed=False,
        reason="generation_failed",
    )
