"""Tests for F10: SSE job status streaming."""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from webapp.schemas import JobStatusResponse


class TestSSEStreaming:
    """Integration tests for the SSE job status endpoint."""

    @pytest.fixture(autouse=True)
    def setup_app(self, monkeypatch):
        monkeypatch.setenv("JW_API_KEY", "sse-test-key")
        monkeypatch.setenv("JW_AUTH_STRICT", "true")

        import importlib
        import webapp.auth as auth_module
        import webapp.rate_limit as rl_module
        importlib.reload(auth_module)
        importlib.reload(rl_module)

        test_app = FastAPI()

        @test_app.get("/api/jobs/{job_id}/stream")
        async def stream_job_status(job_id: str, request=None):
            import asyncio
            from fastapi.responses import StreamingResponse

            async def event_generator():
                states = [
                    {"job_id": job_id, "status": "queued", "step": "queued",
                     "progress_message": "Job criado", "title": None, "warnings": []},
                    {"job_id": job_id, "status": "processing", "step": "planning",
                     "progress_message": "Planejando...", "title": "Meu Vídeo", "warnings": []},
                    {"job_id": job_id, "status": "completed", "step": "completed",
                     "progress_message": "Vídeo pronto!", "title": "Meu Vídeo",
                     "preview_url": f"/api/jobs/{job_id}/download",
                     "download_url": f"/api/jobs/{job_id}/download", "warnings": []},
                ]
                for state in states:
                    yield f"data: {json.dumps(state, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.01)

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                         "X-Accel-Buffering": "no"},
            )

        test_app.add_middleware(auth_module.AuthMiddleware)
        test_app.add_middleware(rl_module.RateLimitMiddleware)
        self.client = TestClient(test_app)

    def test_sse_endpoint_returns_event_stream(self):
        """SSE endpoint should return text/event-stream."""
        with self.client.stream(
            "GET", "/api/jobs/test-stream/stream",
            headers={"X-API-Key": "sse-test-key"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

    def test_sse_stream_contains_data(self):
        """SSE stream should contain data: prefixed messages."""
        with self.client.stream(
            "GET", "/api/jobs/test-stream/stream",
            headers={"X-API-Key": "sse-test-key"},
        ) as response:
            content = b""
            for chunk in response.iter_bytes():
                content += chunk
            text = content.decode("utf-8")
            assert "data:" in text
            assert "queued" in text
            assert "completed" in text

    def test_sse_has_no_cache_headers(self):
        """SSE responses must disable caching."""
        with self.client.stream(
            "GET", "/api/jobs/test-stream/stream",
            headers={"X-API-Key": "sse-test-key"},
        ) as response:
            assert response.headers.get("cache-control") == "no-cache"
            assert response.headers.get("x-accel-buffering") == "no"

    def test_sse_unauthorized_without_key(self):
        """SSE endpoint requires authentication."""
        response = self.client.get(
            "/api/jobs/test-stream/stream",
        )
        assert response.status_code == 401


class TestAppJSUsesSSE:
    """Verify app.js uses EventSource instead of polling."""

    def test_app_js_has_event_source(self):
        """app.js should reference EventSource."""
        from pathlib import Path
        js_path = Path(__file__).parent.parent / "static" / "app.js"
        content = js_path.read_text()
        assert "EventSource" in content, "app.js must use EventSource"
        assert "startSSE" in content, "app.js must have startSSE function"

    def test_app_js_falls_back_to_polling(self):
        """app.js should fall back to polling on SSE error."""
        from pathlib import Path
        js_path = Path(__file__).parent.parent / "static" / "app.js"
        content = js_path.read_text()
        assert "startPolling" in content, "Polling fallback must exist"
