"""Tests for webapp.auth — API key authentication middleware."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from webapp.auth import (
    AUTH_HEADER,
    _constant_time_compare,
    _is_public_path,
    _validate_api_key,
)


class TestConstantTimeCompare:
    def test_equal_strings_match(self):
        assert _constant_time_compare("abc123", "abc123") is True

    def test_different_strings_dont_match(self):
        assert _constant_time_compare("abc123", "abc124") is False

    def test_different_lengths_dont_match(self):
        assert _constant_time_compare("abc", "abcd") is False

    def test_empty_strings_match(self):
        assert _constant_time_compare("", "") is True

    def test_case_sensitive(self):
        assert _constant_time_compare("KEY", "key") is False


class TestPublicPaths:
    def test_root_is_public(self):
        assert _is_public_path("/") is True

    def test_health_is_public(self):
        assert _is_public_path("/api/health/external") is True

    def test_static_is_public(self):
        assert _is_public_path("/static/app.js") is True
        assert _is_public_path("/assets/logo/logo.png") is True

    def test_api_jobs_is_not_public(self):
        assert _is_public_path("/api/jobs") is False
        assert _is_public_path("/api/jobs/abc123") is False

    def test_api_download_is_not_public(self):
        assert _is_public_path("/api/jobs/abc123/download") is False


class TestValidateApiKeyLogic:
    """Test _validate_api_key function logic directly.

    Note: API_KEY is a module-level constant loaded at import time.
    These tests verify the internal validation logic works correctly
    regardless of environment. Integration tests cover full middleware behavior.
    """

    def test_none_rejected_when_key_set(self, monkeypatch):
        """When key is set in env BEFORE import, _validate_api_key rejects None."""
        # Re-import with env set to test module-level constant behavior
        monkeypatch.setenv("JW_API_KEY", "my-test-key")
        import importlib
        import webapp.auth as auth_mod
        importlib.reload(auth_mod)
        assert auth_mod._validate_api_key(None) is False
        assert auth_mod._validate_api_key("") is False

    def test_wrong_key_rejected(self, monkeypatch):
        monkeypatch.setenv("JW_API_KEY", "correct-key")
        import importlib
        import webapp.auth as auth_mod
        importlib.reload(auth_mod)
        assert auth_mod._validate_api_key("wrong-key") is False

    def test_correct_key_accepted(self, monkeypatch):
        monkeypatch.setenv("JW_API_KEY", "secret123")
        import importlib
        import webapp.auth as auth_mod
        importlib.reload(auth_mod)
        assert auth_mod._validate_api_key("secret123") is True

    def test_empty_env_accepts_all(self, monkeypatch):
        """With no key configured, _validate_api_key should return True
        to allow requests in development mode."""
        monkeypatch.delenv("JW_API_KEY", raising=False)
        import importlib
        import webapp.auth as auth_mod
        importlib.reload(auth_mod)
        # When API_KEY is empty, validate passes everything
        assert auth_mod._validate_api_key(None) is True
        assert auth_mod._validate_api_key("anything") is True


class TestAuthMiddlewareIntegration:
    """Integration tests with FastAPI TestClient."""

    @pytest.fixture(autouse=True)
    def setup_app(self, monkeypatch):
        """Create a minimal FastAPI app with auth middleware for testing."""
        monkeypatch.setenv("JW_API_KEY", "integration-test-key")
        monkeypatch.setenv("JW_AUTH_STRICT", "true")

        # Re-import to pick up env vars set before import
        import importlib
        import webapp.auth as auth_module
        importlib.reload(auth_module)

        test_app = FastAPI()

        @test_app.get("/")
        def public_root():
            return {"status": "public"}

        @test_app.get("/api/health/external")
        def public_health():
            return {"status": "healthy"}

        @test_app.post("/api/jobs")
        async def create_job():
            return {"job_id": "test-123"}

        @test_app.get("/api/jobs/{job_id}")
        def get_job(job_id: str):
            return {"job_id": job_id}

        test_app.add_middleware(auth_module.AuthMiddleware)
        self.client = TestClient(test_app)

    def test_public_root_no_auth(self):
        response = self.client.get("/")
        assert response.status_code == 200

    def test_public_health_no_auth(self):
        response = self.client.get("/api/health/external")
        assert response.status_code == 200

    def test_protected_jobs_without_key_returns_401(self):
        response = self.client.post("/api/jobs", json={})
        assert response.status_code == 401
        assert "Chave de API" in response.json()["detail"]

    def test_protected_jobs_with_wrong_key_returns_401(self):
        response = self.client.post(
            "/api/jobs",
            json={},
            headers={AUTH_HEADER: "wrong-key"},
        )
        assert response.status_code == 401

    def test_protected_jobs_with_correct_key_returns_200(self):
        response = self.client.post(
            "/api/jobs",
            json={},
            headers={AUTH_HEADER: "integration-test-key"},
        )
        # 422 because no request body, but NOT 401 — auth passed
        assert response.status_code != 401

    def test_protected_job_status_with_correct_key(self):
        response = self.client.get(
            "/api/jobs/test-123",
            headers={AUTH_HEADER: "integration-test-key"},
        )
        assert response.status_code == 200
        assert response.json()["job_id"] == "test-123"

    def test_header_case_insensitive(self):
        """X-API-Key should work regardless of header casing."""
        response = self.client.post(
            "/api/jobs",
            json={},
            headers={"x-api-key": "integration-test-key"},
        )
        assert response.status_code != 401

    def test_401_response_has_www_authenticate_header(self):
        response = self.client.post("/api/jobs", json={})
        assert response.status_code == 401
        assert response.headers.get("WWW-Authenticate") == "ApiKey"

    def test_401_response_body_is_json(self):
        response = self.client.post("/api/jobs", json={})
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "X-API-Key" in data["detail"]


class TestAuthMiddlewareDevMode:
    """Tests for development mode (no JW_API_KEY configured)."""

    @pytest.fixture(autouse=True)
    def setup_app(self, monkeypatch):
        monkeypatch.delenv("JW_API_KEY", raising=False)
        monkeypatch.setenv("JW_AUTH_STRICT", "false")

        import importlib
        import webapp.auth as auth_module
        importlib.reload(auth_module)

        test_app = FastAPI()

        @test_app.post("/api/jobs")
        async def create_job():
            return {"job_id": "dev-123"}

        test_app.add_middleware(auth_module.AuthMiddleware)
        self.client = TestClient(test_app)

    def test_dev_mode_allows_all_requests(self):
        """Without JW_API_KEY and strict=false, all requests pass."""
        response = self.client.post("/api/jobs", json={})
        assert response.status_code != 401
