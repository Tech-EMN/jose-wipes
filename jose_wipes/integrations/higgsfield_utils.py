"""Higgsfield integration helpers."""

from __future__ import annotations

from pathlib import Path

import httpx


def upload_higgsfield_file(path: str | Path) -> str:
    import higgsfield_client

    file_path = Path(path)
    content_type = higgsfield_client.sync_client.guess_mime_type(file_path)
    response = higgsfield_client.sync_client._transport.request(
        "POST",
        "/files/generate-upload-url",
        json={"content_type": content_type},
    )
    payload = response.json()
    upload_headers = payload.get("upload_headers")
    if not isinstance(upload_headers, dict):
        raise RuntimeError("Higgsfield upload response is missing upload_headers.")

    upload_response = httpx.put(
        payload["upload_url"],
        content=file_path.read_bytes(),
        headers=upload_headers,
        timeout=90,
    )
    upload_response.raise_for_status()
    return str(payload["public_url"])
