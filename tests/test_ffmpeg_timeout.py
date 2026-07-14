"""Tests for FFmpeg subprocess timeout protection (F7)."""

from __future__ import annotations

import subprocess
import pytest
from unittest.mock import patch, MagicMock

from scripts.compositor import _subprocess_run, _DEFAULT_FFMPEG_TIMEOUT


class TestSubprocessRunDefaultTimeout:
    """Tests that _subprocess_run enforces a default timeout."""

    def test_default_timeout_is_set(self):
        """_subprocess_run should apply default timeout when none given."""
        with patch("subprocess.run") as mock_run:
            _subprocess_run(["ffmpeg", "-version"])
            call_kwargs = mock_run.call_args[1]
            assert "timeout" in call_kwargs
            assert call_kwargs["timeout"] == _DEFAULT_FFMPEG_TIMEOUT

    def test_explicit_timeout_not_overridden(self):
        """Explicit timeout parameter should not be overridden."""
        with patch("subprocess.run") as mock_run:
            _subprocess_run(["ffmpeg", "-i", "test.mp4"], timeout=60)
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["timeout"] == 60

    def test_ffprobe_timeout_preserved(self):
        """ffprobe probe calls should keep their shorter timeout."""
        with patch("subprocess.run") as mock_run:
            _subprocess_run(
                ["ffprobe", "-v", "quiet", "-show_format", "test.mp4"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["timeout"] == 10

    def test_other_kwargs_preserved(self):
        """Other kwargs like capture_output, text, check should be passed through."""
        with patch("subprocess.run") as mock_run:
            _subprocess_run(
                ["ffmpeg", "-y", "-i", "in.mp4", "out.mp4"],
                capture_output=True,
                text=True,
                check=True,
            )
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["capture_output"] is True
            assert call_kwargs["text"] is True
            assert call_kwargs["check"] is True
            assert call_kwargs["timeout"] == _DEFAULT_FFMPEG_TIMEOUT

    def test_timeout_applied_to_normalizar_ffmpeg_call(self):
        """The ffmpeg call in normalizar_cena should receive a timeout."""
        with patch("scripts.compositor._subprocess_run") as mock_run:
            from scripts.compositor import normalizar_cena
            import tempfile
            from pathlib import Path

            # Mock probe to return no audio
            probe_mock = MagicMock(returncode=0, stdout='{"streams":[]}', stderr="")
            ffmpeg_mock = MagicMock(returncode=0, stdout="", stderr="")
            mock_run.side_effect = [probe_mock, ffmpeg_mock, ffmpeg_mock]

            normalizar_cena(
                Path("/tmp/test.mp4"),
                Path(tempfile.gettempdir()) / "norm.mp4",
            )
            # Verify all calls have timeout
            for call in mock_run.call_args_list:
                assert "timeout" in call[1], f"Missing timeout in call: {call}"

    def test_timeout_applied_to_concatenar_ffmpeg_calls(self):
        """The ffmpeg calls in concatenar_cenas should receive a timeout."""
        with patch("scripts.compositor._subprocess_run") as mock_run:
            from scripts.compositor import concatenar_cenas
            import tempfile
            from pathlib import Path

            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            concatenar_cenas(
                [Path("/tmp/test1.mp4"), Path("/tmp/test2.mp4")],
                Path(tempfile.gettempdir()) / "concat_test.mp4",
            )
            # All calls should have timeout
            for call in mock_run.call_args_list:
                assert "timeout" in call[1], f"Missing timeout in call: {call}"


class TestDefaultTimeoutValue:
    def test_default_timeout_is_reasonable(self):
        """Default timeout should be 300 seconds (5 minutes)."""
        assert _DEFAULT_FFMPEG_TIMEOUT == 300

    def test_timeout_configurable_via_env(self, monkeypatch):
        """JW_FFMPEG_TIMEOUT env var should allow customization."""
        monkeypatch.setenv("JW_FFMPEG_TIMEOUT", "600")
        import importlib
        import scripts.compositor as comp
        importlib.reload(comp)
        assert comp._DEFAULT_FFMPEG_TIMEOUT == 600

    def test_gerador_midia_also_has_timeout(self, monkeypatch):
        """gerador_midia.py _subprocess_run also applies default timeout."""
        monkeypatch.setenv("JW_FFMPEG_TIMEOUT", "300")
        import importlib
        import scripts.gerador_midia as gm
        importlib.reload(gm)

        with patch("subprocess.run") as mock_run:
            gm._subprocess_run(["ffmpeg", "-version"])
            assert "timeout" in mock_run.call_args[1]
            assert mock_run.call_args[1]["timeout"] == 300
