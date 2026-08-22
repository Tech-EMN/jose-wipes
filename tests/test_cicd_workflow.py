"""Tests for F8: CI/CD workflow file validity."""

from __future__ import annotations

import pytest
from pathlib import Path


class TestCICDWorkflow:
    """Verify the GitHub Actions workflow file exists and is valid."""

    @pytest.fixture
    def workflow_path(self) -> Path:
        p = Path(__file__).parent.parent / ".github" / "workflows" / "hostinger-deploy.yml"
        if not p.exists():
            pytest.skip(".github/workflows/hostinger-deploy.yml not found")
        return p

    def test_workflow_file_exists(self, workflow_path):
        """The CI/CD workflow file should exist."""
        assert workflow_path.exists()

    def test_workflow_has_name(self, workflow_path):
        """Workflow must have a name."""
        import yaml
        content = yaml.safe_load(workflow_path.read_text())
        assert "name" in content

    def test_workflow_triggers_on_push_main(self, workflow_path):
        """Workflow must trigger on push to main."""
        content = workflow_path.read_text()
        assert "push:" in content
        assert "branches: [main]" in content

    def test_workflow_supports_manual_dispatch(self, workflow_path):
        """Workflow must support workflow_dispatch for manual runs."""
        content = workflow_path.read_text()
        assert "workflow_dispatch" in content

    def test_workflow_has_test_job(self, workflow_path):
        """Workflow must include a test job."""
        content = workflow_path.read_text()
        assert "test:" in content or "test" in content
        assert "pytest" in content.lower()

    def test_workflow_has_deploy_job(self, workflow_path):
        """Workflow must include a deploy job."""
        content = workflow_path.read_text()
        assert "deploy:" in content

    def test_workflow_has_health_check(self, workflow_path):
        """Workflow should include a post-deploy health check."""
        content = workflow_path.read_text()
        assert "health" in content.lower()
        assert "api/health" in content

    def test_workflow_skips_without_secrets(self, workflow_path):
        """Workflow should skip deploy gracefully when secrets are missing."""
        content = workflow_path.read_text()
        assert "HOSTINGER_API_KEY" in content
        assert "configured" in content.lower()

    def test_workflow_uses_python_3_12(self, workflow_path):
        """Workflow must use Python 3.12 (matching Dockerfile)."""
        content = workflow_path.read_text()
        assert "3.12" in content

    def test_workflow_installs_ffmpeg(self, workflow_path):
        """Test job must install FFmpeg (required for compositor tests)."""
        content = workflow_path.read_text()
        assert "ffmpeg" in content.lower()

    def test_env_hostinger_example_exists(self):
        """.env.hostinger.example should exist for deploy reference."""
        env_path = Path(__file__).parent.parent / ".env.hostinger.example"
        assert env_path.exists(), ".env.hostinger.example is missing"

    def test_env_hostinger_example_has_required_vars(self):
        """.env.hostinger.example must document all required env vars."""
        env_path = Path(__file__).parent.parent / ".env.hostinger.example"
        content = env_path.read_text()
        required = [
            "TRAEFIK_HOST",
            "HF_API_KEY",
            "OPENAI_API_KEY",
            "ELEVENLABS_API_KEY",
            "JW_API_KEY",
        ]
        for var in required:
            assert var in content, f"Missing {var} in .env.hostinger.example"

    def test_planner_model_matches_runtime_and_requires_explicit_production_env(self):
        root = Path(__file__).parent.parent
        runtime = (root / "scripts" / "config.py").read_text(encoding="utf-8")
        env_example = (root / ".env.hostinger.example").read_text(encoding="utf-8")
        compose = (root / "docker-compose.hostinger.yml").read_text(encoding="utf-8")

        assert 'OPENAI_PLANNER_MODEL", "gpt-4.1-mini"' in runtime
        assert "OPENAI_PLANNER_MODEL=gpt-4.1-mini" in env_example
        assert compose.count("${OPENAI_PLANNER_MODEL:?OPENAI_PLANNER_MODEL must be set}") == 2
        assert "gpt-5.4-pro" not in env_example
        assert "gpt-5.4-pro" not in compose

    def test_production_drive_credentials_are_required_only_by_worker(self):
        root = Path(__file__).parent.parent
        env_example = (root / ".env.hostinger.example").read_text(encoding="utf-8")
        compose = (root / "docker-compose.hostinger.yml").read_text(encoding="utf-8")
        web_section, worker_section = compose.split("  jose-wipes-worker:", 1)

        assert "GOOGLE_SERVICE_ACCOUNT_FILE" not in web_section
        assert "GOOGLE_DRIVE_FOLDER_ID" not in web_section
        assert "GOOGLE_SERVICE_ACCOUNT_FILE: /app/credentials/service-account.json" in worker_section
        assert "${GOOGLE_DRIVE_FOLDER_ID:?GOOGLE_DRIVE_FOLDER_ID must be set}" in worker_section
        assert "${GOOGLE_SERVICE_ACCOUNT_HOST_PATH:?GOOGLE_SERVICE_ACCOUNT_HOST_PATH must be set}" in worker_section
        assert "GOOGLE_SERVICE_ACCOUNT_FILE=/app/credentials/service-account.json" in env_example
