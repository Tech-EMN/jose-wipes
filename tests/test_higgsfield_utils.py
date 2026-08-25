from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from scripts.higgsfield_utils import upload_higgsfield_file


def test_upload_higgsfield_file_forwards_signed_headers(tmp_path):
    file_path = tmp_path / "reference.png"
    file_path.write_bytes(b"image")
    upload_headers = {
        "Content-Type": "image/png",
        "x-amz-tagging": "source=test",
    }
    presign_response = MagicMock()
    presign_response.json.return_value = {
        "public_url": "https://cdn.example.com/reference.png",
        "upload_url": "https://upload.example.com/reference.png",
        "upload_headers": upload_headers,
    }
    sync_client = SimpleNamespace(
        guess_mime_type=MagicMock(return_value="image/png"),
        _transport=SimpleNamespace(
            request=MagicMock(return_value=presign_response),
        ),
    )

    with patch.dict(sys.modules, {"higgsfield_client": SimpleNamespace(sync_client=sync_client)}), patch(
        "scripts.higgsfield_utils.httpx.put"
    ) as upload:
        result = upload_higgsfield_file(file_path)

    assert result == "https://cdn.example.com/reference.png"
    assert upload.call_args.kwargs["headers"] == upload_headers
    upload.return_value.raise_for_status.assert_called_once_with()


def test_upload_higgsfield_file_rejects_malformed_presign_response(tmp_path):
    file_path = tmp_path / "reference.png"
    file_path.write_bytes(b"image")
    presign_response = MagicMock()
    presign_response.json.return_value = {
        "public_url": "https://cdn.example.com/reference.png",
        "upload_url": "https://upload.example.com/reference.png",
        "upload_headers": [],
    }
    sync_client = SimpleNamespace(
        guess_mime_type=MagicMock(return_value="image/png"),
        _transport=SimpleNamespace(
            request=MagicMock(return_value=presign_response),
        ),
    )

    with patch.dict(
        sys.modules,
        {"higgsfield_client": SimpleNamespace(sync_client=sync_client)},
    ), patch("scripts.higgsfield_utils.httpx.put") as upload, pytest.raises(
        RuntimeError,
        match="missing upload_headers",
    ):
        upload_higgsfield_file(file_path)

    upload.assert_not_called()


def test_upload_higgsfield_file_propagates_http_upload_failure(tmp_path):
    file_path = tmp_path / "reference.png"
    file_path.write_bytes(b"image")
    upload_url = "https://upload.example.com/reference.png"
    presign_response = MagicMock()
    presign_response.json.return_value = {
        "public_url": "https://cdn.example.com/reference.png",
        "upload_url": upload_url,
        "upload_headers": {"Content-Type": "image/png"},
    }
    sync_client = SimpleNamespace(
        guess_mime_type=MagicMock(return_value="image/png"),
        _transport=SimpleNamespace(
            request=MagicMock(return_value=presign_response),
        ),
    )
    request = httpx.Request("PUT", upload_url)
    response = httpx.Response(500, request=request)
    failure = httpx.HTTPStatusError(
        "upload failed",
        request=request,
        response=response,
    )

    with patch.dict(
        sys.modules,
        {"higgsfield_client": SimpleNamespace(sync_client=sync_client)},
    ), patch("scripts.higgsfield_utils.httpx.put") as upload:
        upload.return_value.raise_for_status.side_effect = failure
        with pytest.raises(httpx.HTTPStatusError) as captured:
            upload_higgsfield_file(file_path)

    assert captured.value is failure
