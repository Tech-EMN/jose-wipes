"""Direct Higgsfield HTTP reads that keep the provider response intact."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

import httpx

HIGGSFIELD_BASE_URL = "https://platform.higgsfield.ai"
HIGGSFIELD_READ_TIMEOUT_SECONDS = 30.0
HIGGSFIELD_AUTH_PROBE_TIMEOUT_SECONDS = 10.0
HIGGSFIELD_AUTH_PROBE_REQUEST_ID = "00000000-0000-0000-0000-000000000000"
MAX_PROVIDER_DETAIL_LENGTH = 500
UNAUTHORIZED_STATUS_CODES = frozenset({401, 403})
FAILURE_DETAIL_KEYS = ("error", "message", "detail", "details", "reason", "failure_reason")


class HiggsfieldRequestStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NSFW = "nsfw"
    CANCELED = "canceled"
    UNKNOWN = "unknown"


TERMINAL_STATUSES = frozenset(
    {
        HiggsfieldRequestStatus.COMPLETED,
        HiggsfieldRequestStatus.FAILED,
        HiggsfieldRequestStatus.NSFW,
        HiggsfieldRequestStatus.CANCELED,
    }
)


class HiggsfieldApiError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


@dataclass(frozen=True)
class HiggsfieldStatusSnapshot:
    status: HiggsfieldRequestStatus
    raw_status: str
    payload: dict[str, object] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def failure_detail(self) -> str:
        for key in FAILURE_DETAIL_KEYS:
            detail = _as_text(self.payload.get(key))
            if detail:
                return _truncate(detail)
        return _truncate(f"status={self.raw_status}; payload={json.dumps(self.payload, ensure_ascii=False, default=str)}")


class HiggsfieldAuthOutcome(str, Enum):
    AUTHENTICATED = "authenticated"
    UNAUTHORIZED = "unauthorized"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class HiggsfieldAuthProbeResult:
    outcome: HiggsfieldAuthOutcome
    detail: str

    @property
    def ok(self) -> bool:
        return self.outcome is HiggsfieldAuthOutcome.AUTHENTICATED


def default_status_url(request_id: str) -> str:
    return f"{HIGGSFIELD_BASE_URL}/requests/{request_id}/status"


def fetch_request_status(status_url: str) -> HiggsfieldStatusSnapshot:
    response = _get(_absolute_url(status_url), timeout=HIGGSFIELD_READ_TIMEOUT_SECONDS)
    if response.is_error:
        raise HiggsfieldApiError(response.status_code, extract_response_detail(response))

    payload = _json_object(response)
    raw_status = _as_text(payload.get("status")) or "missing"
    return HiggsfieldStatusSnapshot(
        status=_parse_status(raw_status),
        raw_status=raw_status,
        payload=payload,
    )


def probe_higgsfield_auth() -> HiggsfieldAuthProbeResult:
    try:
        response = _get(
            default_status_url(HIGGSFIELD_AUTH_PROBE_REQUEST_ID),
            timeout=HIGGSFIELD_AUTH_PROBE_TIMEOUT_SECONDS,
        )
    except httpx.TransportError as exc:
        return HiggsfieldAuthProbeResult(
            outcome=HiggsfieldAuthOutcome.UNAVAILABLE,
            detail=f"network error: {exc}",
        )

    detail = f"HTTP {response.status_code}: {extract_response_detail(response)}"
    if response.status_code in UNAUTHORIZED_STATUS_CODES:
        return HiggsfieldAuthProbeResult(outcome=HiggsfieldAuthOutcome.UNAUTHORIZED, detail=detail)
    if response.status_code >= 500 or response.status_code == 429:
        return HiggsfieldAuthProbeResult(outcome=HiggsfieldAuthOutcome.UNAVAILABLE, detail=detail)
    return HiggsfieldAuthProbeResult(outcome=HiggsfieldAuthOutcome.AUTHENTICATED, detail=detail)


def extract_response_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return _truncate(response.text or response.reason_phrase)

    if isinstance(payload, dict):
        for key in FAILURE_DETAIL_KEYS:
            detail = _as_text(payload.get(key))
            if detail:
                return _truncate(detail)
    return _truncate(json.dumps(payload, ensure_ascii=False, default=str))


def _absolute_url(url: str) -> str:
    if url.startswith(("http://", "https://")):
        return url
    return f"{HIGGSFIELD_BASE_URL}/{url.lstrip('/')}"


def _get(url: str, *, timeout: float) -> httpx.Response:
    from higgsfield_client.auth import get_credential_key

    return httpx.get(
        url,
        headers={"Authorization": f"Key {get_credential_key()}"},
        timeout=timeout,
    )


def _json_object(response: httpx.Response) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise HiggsfieldApiError(response.status_code, f"invalid JSON body: {_truncate(response.text)}") from exc
    if not isinstance(payload, dict):
        raise HiggsfieldApiError(response.status_code, f"unexpected JSON body: {_truncate(str(payload))}")
    return payload


def _parse_status(raw_status: str) -> HiggsfieldRequestStatus:
    try:
        return HiggsfieldRequestStatus(raw_status.lower())
    except ValueError:
        return HiggsfieldRequestStatus.UNKNOWN


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        nested = value.get("message") or value.get("detail")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return json.dumps(value, ensure_ascii=False, default=str)


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_PROVIDER_DETAIL_LENGTH else f"{text[:MAX_PROVIDER_DETAIL_LENGTH]}..."
