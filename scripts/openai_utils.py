"""Shared helpers for OpenAI Responses API usage in planning flows."""

from __future__ import annotations

from scripts.integration_errors import IntegrationFailure

def extract_response_output_text(response: object) -> str:
    """Extract plain text from an OpenAI Responses API object."""

    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text).strip()

    output = getattr(response, "output", None) or []
    fragments: list[str] = []
    for item in output:
        content = getattr(item, "content", None) or []
        for part in content:
            if getattr(part, "type", None) == "output_text":
                text = getattr(part, "text", None)
                if text:
                    fragments.append(str(text))

    combined = "\n".join(fragment.strip() for fragment in fragments if fragment and fragment.strip())
    return combined.strip()


def create_text_response(
    *,
    client: object,
    model: str,
    instructions: str,
    user_input: str,
    max_output_tokens: int,
    reasoning_effort: str = "medium",
) -> str:
    """Create a plain-text response using the OpenAI Responses API."""
    try:
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=user_input,
            max_output_tokens=max_output_tokens,
            reasoning={"effort": reasoning_effort},
        )
    except Exception as exc:
        raise classify_openai_exception(exc) from exc

    status = getattr(response, "status", None)
    incomplete_details = getattr(response, "incomplete_details", None)
    text = extract_response_output_text(response)
    if status and str(status).lower() != "completed":
        reason = None
        if incomplete_details and hasattr(incomplete_details, "reason"):
            reason = getattr(incomplete_details, "reason", None)
        elif isinstance(incomplete_details, dict):
            reason = incomplete_details.get("reason")
        partial_preview = (text[:200] + "...") if text else "(sem texto parcial)"
        raise IntegrationFailure(
            service="openai",
            stage="planning",
            code="empty_or_incomplete_response",
            user_message=(
                "A OpenAI respondeu, mas não devolveu um plano completo. Tente novamente em instantes."
            ),
            technical_message=(
                f"Response status={status}, reason={reason or 'unknown'}, "
                f"partial_output={partial_preview}"
            ),
            retryable=True,
        )
    if not text:
        raise IntegrationFailure(
            service="openai",
            stage="planning",
            code="empty_or_incomplete_response",
            user_message="A OpenAI não retornou texto útil para o planejamento.",
            technical_message="Responses API sem output_text final.",
            retryable=True,
        )
    return text


def classify_openai_exception(exc: Exception, *, stage: str = "planning") -> IntegrationFailure:
    """Map OpenAI SDK exceptions to a structured contract."""

    from openai import APIConnectionError, AuthenticationError, RateLimitError

    message = str(exc).strip() or exc.__class__.__name__

    if isinstance(exc, APIConnectionError):
        return IntegrationFailure(
            service="openai",
            stage=stage,
            code="connection_error",
            user_message=(
                "Falha ao conectar na OpenAI durante o planejamento. Verifique conectividade externa ou o status da OpenAI."
            ),
            technical_message=message,
            retryable=True,
        )

    if isinstance(exc, RateLimitError):
        return IntegrationFailure(
            service="openai",
            stage=stage,
            code="rate_limit",
            user_message="A OpenAI limitou temporariamente as requisições. Tente novamente em instantes.",
            technical_message=message,
            retryable=True,
        )

    if isinstance(exc, AuthenticationError):
        return IntegrationFailure(
            service="openai",
            stage=stage,
            code="auth_invalid",
            user_message="Falha de autenticação na OpenAI. Verifique a OPENAI_API_KEY configurada.",
            technical_message=message,
            retryable=False,
            auth_confirmed=False,
        )

    return IntegrationFailure(
        service="openai",
        stage=stage,
        code="unexpected_error",
        user_message="A OpenAI falhou durante o planejamento do anúncio.",
        technical_message=message,
        retryable=False,
    )
