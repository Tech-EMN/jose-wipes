import httpx
import pytest
from unittest.mock import patch

from higgsfield_client import HiggsfieldClientError
from scripts.higgsfield_api import (
    HiggsfieldApiError,
    HiggsfieldAuthOutcome,
    HiggsfieldRequestStatus,
    HiggsfieldStatusSnapshot,
    fetch_request_status,
    probe_higgsfield_auth,
)
from scripts.integration_errors import classify_higgsfield_exception

STATUS_URL = "https://api.higgsfield.ai/requests/request-1/status"


def _response(status_code: int, payload: object) -> httpx.Response:
    return httpx.Response(status_code, json=payload, request=httpx.Request("GET", STATUS_URL))


def _sdk_error(status_code: int, detail: object) -> HiggsfieldClientError:
    response = _response(status_code, {"detail": detail})
    cause = httpx.HTTPStatusError("provider error", request=response.request, response=response)
    error = HiggsfieldClientError(str(detail))
    error.__cause__ = cause
    return error


def test_fetch_request_status_keeps_failure_payload() -> None:
    payload = {"status": "failed", "error": {"message": "Prompt rejected by provider"}}
    with patch("scripts.higgsfield_api._get", return_value=_response(200, payload)):
        snapshot = fetch_request_status(STATUS_URL)

    assert snapshot.status is HiggsfieldRequestStatus.FAILED
    assert snapshot.is_terminal is True
    assert snapshot.failure_detail() == "Prompt rejected by provider"


def test_fetch_request_status_maps_unknown_status_without_raising() -> None:
    with patch("scripts.higgsfield_api._get", return_value=_response(200, {"status": "rendering"})):
        snapshot = fetch_request_status(STATUS_URL)

    assert snapshot.status is HiggsfieldRequestStatus.UNKNOWN
    assert snapshot.raw_status == "rendering"
    assert snapshot.is_terminal is False


def test_fetch_request_status_raises_with_http_status_and_detail() -> None:
    with patch(
        "scripts.higgsfield_api._get",
        return_value=_response(401, {"detail": "Invalid API key"}),
    ), pytest.raises(HiggsfieldApiError) as captured:
        fetch_request_status(STATUS_URL)

    assert captured.value.status_code == 401
    assert str(captured.value) == "HTTP 401: Invalid API key"


def test_failure_detail_falls_back_to_serialized_payload() -> None:
    snapshot = HiggsfieldStatusSnapshot(
        HiggsfieldRequestStatus.FAILED,
        "failed",
        {"status": "failed", "request_id": "request-1"},
    )

    assert "request-1" in snapshot.failure_detail()


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, HiggsfieldAuthOutcome.UNAUTHORIZED),
        (403, HiggsfieldAuthOutcome.AUTHENTICATED),
        (404, HiggsfieldAuthOutcome.AUTHENTICATED),
        (422, HiggsfieldAuthOutcome.AUTHENTICATED),
        (429, HiggsfieldAuthOutcome.UNAVAILABLE),
        (503, HiggsfieldAuthOutcome.UNAVAILABLE),
    ],
)
def test_auth_probe_maps_http_status(status_code: int, expected: HiggsfieldAuthOutcome) -> None:
    with patch(
        "scripts.higgsfield_api._get",
        return_value=_response(status_code, {"detail": "provider says"}),
    ):
        result = probe_higgsfield_auth()

    assert result.outcome is expected
    assert result.detail == f"HTTP {status_code}: provider says"


def test_auth_probe_reports_network_failure() -> None:
    with patch(
        "scripts.higgsfield_api._get",
        side_effect=httpx.ConnectError("Network is unreachable"),
    ):
        result = probe_higgsfield_auth()

    assert result.outcome is HiggsfieldAuthOutcome.UNAVAILABLE
    assert result.ok is False


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (_sdk_error(401, "Invalid API key"), "auth_invalid"),
        (_sdk_error(403, "Forbidden"), "insufficient_credits"),
        (_sdk_error(423, "Locked"), "model_blocked"),
        (RuntimeError("model_blocked"), "model_blocked"),
        (_sdk_error(402, "Payment required"), "insufficient_credits"),
        (_sdk_error(404, "Not Found"), "model_not_found"),
        (_sdk_error(422, [{"loc": ["body", "reference_image_urls"], "msg": "Extra inputs are not permitted"}]), "invalid_arguments"),
        (_sdk_error(429, "Too many requests"), "rate_limited"),
        (_sdk_error(502, "Bad gateway"), "provider_unavailable"),
        (HiggsfieldApiError(401, "Invalid API key"), "auth_invalid"),
        (RuntimeError("HTTP 422: invalid duration"), "invalid_arguments"),
        (httpx.ConnectError("boom"), "network_error"),
        (RuntimeError("Insufficient permissions for this model"), "generation_failed"),
        (RuntimeError("Insufficient credits"), "insufficient_credits"),
    ],
)
def test_higgsfield_classification_uses_http_status(error: Exception, expected_code: str) -> None:
    failure = classify_higgsfield_exception(error)

    assert failure.code == expected_code
    assert failure.reason == expected_code


def test_invalid_arguments_keeps_validation_detail_in_technical_message() -> None:
    failure = classify_higgsfield_exception(
        _sdk_error(422, [{"loc": ["body", "resolution"], "msg": "Input should be '720p'"}])
    )

    assert failure.retryable is False
    assert failure.auth_confirmed is True
    assert "resolution" in (failure.technical_message or "")


def test_fetch_request_status_resolves_relative_status_url() -> None:
    with patch(
        "scripts.higgsfield_api._get",
        return_value=_response(200, {"status": "queued"}),
    ) as get:
        fetch_request_status("/requests/request-1/status")

    assert get.call_args.args[0] == STATUS_URL


def test_model_blocked_is_not_retried_with_same_input() -> None:
    failure = classify_higgsfield_exception(RuntimeError("model_blocked"))

    assert failure.retryable is False
    assert failure.auth_confirmed is True
    assert failure.technical_message == "model_blocked"
