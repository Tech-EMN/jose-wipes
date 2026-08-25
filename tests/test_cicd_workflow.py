"""Tests for F8: CI/CD workflow file validity."""

from __future__ import annotations

import pytest
from pathlib import Path


class TestCICDWorkflow:
    """Verify the GitHub Actions workflow file exists and is valid."""

    @pytest.fixture
    def workflow_path(self) -> Path:
        p = Path(__file__).parent.parent / ".github" / "workflows" / "easypanel-deploy.yml"
        if not p.exists():
            pytest.skip(".github/workflows/easypanel-deploy.yml not found")
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

    def test_workflow_requires_easypanel_deploy_url(self, workflow_path):
        """Workflow must fail clearly when the EasyPanel trigger is missing."""
        content = workflow_path.read_text()
        assert "EASYPANEL_DEPLOY_URL" in content
        assert "EASYPANEL_DEPLOY_URL is not configured" in content
        assert "exit 1" in content

    def test_workflow_uses_python_3_12(self, workflow_path):
        """Workflow must use Python 3.12 (matching Dockerfile)."""
        content = workflow_path.read_text()
        assert "3.12" in content

    def test_workflow_installs_ffmpeg(self, workflow_path):
        """Test job must install FFmpeg (required for compositor tests)."""
        content = workflow_path.read_text()
        assert "ffmpeg" in content.lower()

    def test_test_failures_are_not_masked(self, workflow_path):
        content = workflow_path.read_text()
        assert '-m "not e2e"' in content
        assert "|| echo \"Some integration tests skipped" not in content

    def test_deploy_api_failure_is_not_masked(self, workflow_path):
        content = workflow_path.read_text()
        assert "curl --fail-with-body" in content
        assert "--connect-timeout 10 --max-time 30" in content
        assert "HOSTINGER_API_KEY" not in content

    def test_health_check_uses_optional_app_url(self, workflow_path):
        content = workflow_path.read_text()
        assert "vars.APP_URL" in content
        assert "${APP_URL%/}/api/health/external" in content
        assert "--connect-timeout 5 --max-time 10" in content

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

    def test_production_drive_policy_is_configured_only_by_worker(self):
        root = Path(__file__).parent.parent
        env_example = (root / ".env.hostinger.example").read_text(encoding="utf-8")
        compose = (root / "docker-compose.hostinger.yml").read_text(encoding="utf-8")
        web_section, worker_section = compose.split("  jose-wipes-worker:", 1)

        assert "GOOGLE_SERVICE_ACCOUNT_FILE" not in web_section
        assert "GOOGLE_DRIVE_FOLDER_ID" not in web_section
        assert "GOOGLE_SERVICE_ACCOUNT_FILE: /app/credentials/service-account.json" in worker_section
        assert "GOOGLE_DRIVE_FOLDER_ID: ${GOOGLE_DRIVE_FOLDER_ID:-}" in worker_section
        assert "JW_DRIVE_REQUIRED: ${JW_DRIVE_REQUIRED:-false}" in worker_section
        assert "${GOOGLE_SERVICE_ACCOUNT_HOST_PATH:-/dev/null}" in worker_section
        assert "JW_DRIVE_REQUIRED=false" in env_example
        assert "GOOGLE_SERVICE_ACCOUNT_FILE=/app/credentials/service-account.json" in env_example

    def test_production_runtime_guards_are_forwarded(self):
        root = Path(__file__).parent.parent
        compose = (root / "docker-compose.hostinger.yml").read_text(encoding="utf-8")
        web_section, worker_section = compose.split("  jose-wipes-worker:", 1)

        assert "JW_API_KEY: ${JW_API_KEY:-}" in web_section
        assert "JW_AUTH_STRICT: ${JW_AUTH_STRICT:-false}" in web_section
        assert "JW_FFMPEG_TIMEOUT: ${JW_FFMPEG_TIMEOUT:-300}" in worker_section
        assert "JW_HIGGSFIELD_POLL_TIMEOUT_SECONDS:" in worker_section
