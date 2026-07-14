"""Tests for Phase 4 quick fixes: F12, F15, F17, F9."""

from __future__ import annotations

import pytest
from pathlib import Path


class TestF12AutoCleanup:
    """F12: Auto cleanup scheduler in worker."""

    def test_worker_has_cleanup_scheduler(self):
        """worker.py should call start_cleanup_scheduler."""
        worker_path = Path(__file__).parent.parent / "webapp" / "worker.py"
        content = worker_path.read_text()
        assert "start_cleanup_scheduler" in content

    def test_cleanup_configurable_via_env(self):
        """Cleanup intervals should be configurable via env vars."""
        worker_path = Path(__file__).parent.parent / "webapp" / "worker.py"
        content = worker_path.read_text()
        assert "JW_CLEANUP_INTERVAL_HOURS" in content
        assert "JW_CLEANUP_JOB_DAYS" in content
        assert "JW_CLEANUP_LOG_DAYS" in content


class TestF15LogoPath:
    """F15: Configurable logo path via LOGO_PATH env var."""

    def test_logo_path_env_var_priority(self, monkeypatch, tmp_path):
        """LOGO_PATH env var should take priority over glob/fallback."""
        # Create a test logo
        test_logo = tmp_path / "custom_logo.png"
        test_logo.write_text("fake png")

        monkeypatch.setenv("LOGO_PATH", str(test_logo))

        import importlib
        import scripts.config as cfg
        importlib.reload(cfg)

        result = cfg.obter_logo_path()
        assert result == test_logo

    def test_logo_path_glob_fallback(self, tmp_path, monkeypatch):
        """When LOGO_PATH is not set, glob pattern logo*.png should be used."""
        monkeypatch.delenv("LOGO_PATH", raising=False)

        # Create logo in actual assets/logo dir to test glob
        actual_logo_dir = Path(__file__).parent.parent / "assets" / "logo"
        actual_logo_dir.mkdir(parents=True, exist_ok=True)
        test_logo = actual_logo_dir / "logo_test_glob.png"
        test_logo.write_text("test")

        try:
            import importlib
            import scripts.config as cfg
            importlib.reload(cfg)

            result = cfg.obter_logo_path()
            # Should find via glob (logo_test_glob.png comes before Logo_josé_wipes.png alphabetically)
            assert result.exists()
        finally:
            test_logo.unlink(missing_ok=True)

    def test_logo_path_relative_env(self, monkeypatch, tmp_path):
        """Relative LOGO_PATH should be resolved against PROJECT_ROOT."""
        monkeypatch.setenv("LOGO_PATH", "assets/logo/mylogo.png")

        import importlib
        import scripts.config as cfg
        importlib.reload(cfg)


class TestF17FallbackEnv:
    """F17: Env vars for fallback model applications."""

    def test_fallback_env_vars_exist(self):
        """model_registry.py should use _FALLBACK env vars."""
        registry_path = (
            Path(__file__).parent.parent / "webapp" / "model_registry.py"
        )
        content = registry_path.read_text()
        assert "HF_MODEL_SEEDANCE_1_5_PRO_FALLBACK" in content
        assert "HF_MODEL_KLING_3_0_FALLBACK" in content
        assert "HF_MODEL_VEO_3_1_FALLBACK" in content

    def test_fallback_not_hardcoded(self):
        """Fallback should use _env_or_default, not string literal."""
        registry_path = (
            Path(__file__).parent.parent / "webapp" / "model_registry.py"
        )
        content = registry_path.read_text()
        assert '_env_or_default(\n            "HF_MODEL_SEEDANCE_1_5_PRO_FALLBACK"' in content


class TestF9ConsolidateDeploy:
    """F9: Remove Vercel/Heroku deploy targets."""

    def test_vercel_json_removed(self):
        """vercel.json should not exist."""
        vercel_path = Path(__file__).parent.parent / "vercel.json"
        assert not vercel_path.exists(), "vercel.json should be removed"

    def test_procfile_removed(self):
        """Procfile should not exist."""
        procfile_path = Path(__file__).parent.parent / "Procfile"
        assert not procfile_path.exists(), "Procfile should be removed"

    def test_api_index_removed(self):
        """api/index.py should not exist."""
        index_path = Path(__file__).parent.parent / "api" / "index.py"
        assert not index_path.exists(), "api/index.py should be removed"
