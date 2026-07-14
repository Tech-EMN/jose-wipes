"""Tests for webapp.rate_limit — sliding-window rate limit middleware."""

from __future__ import annotations

import os
import time
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestRateLimitIntegration:
    """Integration tests for the rate limit middleware."""

    @pytest.fixture(autouse=True)
    def setup_app(self, monkeypatch):
        """Create a FastAPI app with rate limiting for testing."""
        monkeypatch.setenv("JW_RATE_LIMIT_JOBS", "3")
        monkeypatch.setenv("JW_RATE_LIMIT_WINDOW_SECONDS", "60")
        monkeypatch.setenv("JW_RATE_LIMIT_ENABLED", "true")

        import importlib
        import webapp.rate_limit as rl_module
        importlib.reload(rl_module)

        test_app = FastAPI()

        @test_app.get("/")
        def public_root():
            return {"status": "ok"}

        @test_app.post("/api/jobs")
        async def create_job():
            return {"job_id": "test"}

        @test_app.get("/api/jobs/{job_id}")
        def get_job(job_id: str):
            return {"job_id": job_id}

        @test_app.get("/api/health/external")
        def health():
            return {"status": "healthy"}

        test_app.add_middleware(rl_module.RateLimitMiddleware)
        self.client = TestClient(test_app)

    def test_public_routes_not_rate_limited(self):
        """Root and health endpoints should not be rate limited."""
        for _ in range(10):
            response = self.client.get("/")
            assert response.status_code == 200
        for _ in range(10):
            response = self.client.get("/api/health/external")
            assert response.status_code == 200

    def test_jobs_within_limit_succeed(self):
        """Up to the limit (3) POSTs should succeed."""
        for i in range(3):
            response = self.client.post("/api/jobs")
            assert response.status_code != 429, f"Request {i+1} should not be rate limited"

    def test_jobs_exceeding_limit_return_429(self):
        """Request beyond the limit should return 429."""
        # Exhaust the limit
        for _ in range(3):
            response = self.client.post("/api/jobs")
            assert response.status_code != 429

        # 4th request should be rate limited
        response = self.client.post("/api/jobs")
        assert response.status_code == 429
        data = response.json()
        assert "Limite" in data["detail"]
        assert "retry_after_seconds" in data

    def test_429_has_retry_after_header(self):
        """Rate-limited response must include Retry-After header."""
        for _ in range(3):
            self.client.post("/api/jobs")

        response = self.client.post("/api/jobs")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) >= 0

    def test_429_has_rate_limit_headers(self):
        """Rate-limited response must include X-RateLimit-* headers."""
        for _ in range(3):
            self.client.post("/api/jobs")

        response = self.client.post("/api/jobs")
        assert response.status_code == 429
        assert response.headers["X-RateLimit-Limit"] == "3"
        assert response.headers["X-RateLimit-Remaining"] == "0"

    def test_success_response_has_rate_limit_headers(self):
        """Successful requests should include X-RateLimit-* headers."""
        response = self.client.post("/api/jobs")
        assert response.status_code != 429
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert int(response.headers["X-RateLimit-Remaining"]) >= 0

    def test_get_jobs_not_rate_limited(self):
        """GET /api/jobs/{id} should NOT be rate limited."""
        for _ in range(10):
            response = self.client.get("/api/jobs/test-id")
            assert response.status_code != 429

    def test_remaining_decrements(self):
        """X-RateLimit-Remaining should decrement with each request."""
        r1 = self.client.post("/api/jobs")
        assert r1.status_code != 429
        remaining_1 = int(r1.headers["X-RateLimit-Remaining"])

        r2 = self.client.post("/api/jobs")
        assert r2.status_code != 429
        remaining_2 = int(r2.headers["X-RateLimit-Remaining"])

        assert remaining_2 == remaining_1 - 1


class TestRateLimitDisabled:
    """When rate limiting is disabled, all requests pass."""

    @pytest.fixture(autouse=True)
    def setup_app(self, monkeypatch):
        monkeypatch.setenv("JW_RATE_LIMIT_ENABLED", "false")

        import importlib
        import webapp.rate_limit as rl_module
        importlib.reload(rl_module)

        test_app = FastAPI()

        @test_app.post("/api/jobs")
        async def create_job():
            return {"job_id": "test"}

        test_app.add_middleware(rl_module.RateLimitMiddleware)
        self.client = TestClient(test_app)

    def test_disabled_allows_unlimited_requests(self):
        """With rate limiting disabled, many requests all pass."""
        for _ in range(20):
            response = self.client.post("/api/jobs")
            assert response.status_code != 429


class TestRateLimitCustomConfig:
    """Custom rate limit configuration via env vars."""

    @pytest.fixture(autouse=True)
    def setup_app(self, monkeypatch):
        monkeypatch.setenv("JW_RATE_LIMIT_JOBS", "5")
        monkeypatch.setenv("JW_RATE_LIMIT_WINDOW_SECONDS", "30")

        import importlib
        import webapp.rate_limit as rl_module
        importlib.reload(rl_module)

        test_app = FastAPI()

        @test_app.post("/api/jobs")
        async def create_job():
            return {"job_id": "test"}

        test_app.add_middleware(rl_module.RateLimitMiddleware)
        self.client = TestClient(test_app)

    def test_custom_limit_respected(self):
        """Custom limit of 5 should be enforced."""
        for i in range(5):
            response = self.client.post("/api/jobs")
            assert response.status_code != 429, f"Request {i+1} should pass"

        response = self.client.post("/api/jobs")
        assert response.status_code == 429

    def test_custom_limit_in_headers(self):
        """X-RateLimit-Limit should reflect the configured value."""
        response = self.client.post("/api/jobs")
        assert response.headers["X-RateLimit-Limit"] == "5"
