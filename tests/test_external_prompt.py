"""Tests for F11: external planner system prompt."""

from __future__ import annotations

import hashlib
import pytest
from pathlib import Path


class TestExternalPromptFile:
    """Tests that the planner prompt is properly externalized."""

    def test_prompt_file_exists(self):
        """config/planner_system_prompt.txt must exist."""
        prompt_path = (
            Path(__file__).parent.parent / "config" / "planner_system_prompt.txt"
        )
        assert prompt_path.exists(), "planner_system_prompt.txt is missing"

    def test_prompt_file_not_empty(self):
        """Prompt file must contain substantial content."""
        prompt_path = (
            Path(__file__).parent.parent / "config" / "planner_system_prompt.txt"
        )
        content = prompt_path.read_text()
        assert len(content) > 1000, f"Prompt too short: {len(content)} chars"

    def test_prompt_has_placeholders(self):
        """Prompt must use format-style placeholders for dynamic values."""
        prompt_path = (
            Path(__file__).parent.parent / "config" / "planner_system_prompt.txt"
        )
        content = prompt_path.read_text()
        expected_placeholders = [
            "{aspect_label}",
            "{aspect_ratio}",
            "{composition_hint}",
            "{aspect_tail}",
            "{shot_duration}",
            "{max_words}",
        ]
        for ph in expected_placeholders:
            assert ph in content, f"Missing placeholder: {ph}"

    def test_prompt_format_succeeds(self):
        """Formatting the prompt with all required params should succeed."""
        from webapp.planner import _planner_system_prompt

        # Should not raise
        result = _planner_system_prompt(orientation="vertical")
        assert len(result) > 1000
        # No unformatted placeholders
        assert "{" not in result, "Unfilled placeholders remain"

        # Vertical
        assert "vertical" in result
        assert "9:16" in result

        # Horizontal
        horiz = _planner_system_prompt(orientation="horizontal")
        assert "horizontal" in horiz
        assert "16:9" in horiz
        assert "widescreen" in horiz

    def test_prompt_horizontal_differs_from_vertical(self):
        """Vertical and horizontal prompts should produce different output."""
        from webapp.planner import _planner_system_prompt

        vertical = _planner_system_prompt(orientation="vertical")
        horizontal = _planner_system_prompt(orientation="horizontal")

        assert vertical != horizontal
        assert "VERTICAL" in vertical
        assert "HORIZONTAL" in horizontal


class TestPromptHash:
    """Tests for prompt content hashing (version tracking)."""

    def test_hash_function_returns_string(self):
        """_prompt_content_hash should return a string."""
        from webapp.planner import _prompt_content_hash

        h = _prompt_content_hash()
        assert isinstance(h, str)
        assert len(h) == 12

    def test_hash_is_deterministic(self):
        """Same prompt content should produce the same hash."""
        from webapp.planner import _prompt_content_hash

        h1 = _prompt_content_hash()
        h2 = _prompt_content_hash()
        assert h1 == h2

    def test_hash_changes_when_prompt_changes(self, tmp_path, monkeypatch):
        """Modifying the prompt file should change the hash."""
        # Write a temporary prompt
        prompt_path = tmp_path / "planner_system_prompt.txt"
        prompt_path.write_text("Test prompt version 1")
        monkeypatch.setattr(
            "webapp.planner._prompt_content_hash",
            lambda: hashlib.sha256(prompt_path.read_bytes()).hexdigest()[:12],
        )

        h1 = hashlib.sha256(b"Test prompt version 1").hexdigest()[:12]
        h2 = hashlib.sha256(b"Test prompt version 2").hexdigest()[:12]
        assert h1 != h2


class TestJobMetadataIncludesPromptHash:
    """Verify that created jobs include the prompt hash in metadata."""

    def test_create_job_includes_prompt_hash(self, tmp_path):
        """Job metadata must include planner_prompt_hash."""
        from webapp.job_manager import JobManager
        from webapp.schemas import CreateJobRequest

        manager = JobManager(jobs_dir=tmp_path)
        request = CreateJobRequest.model_validate({
            "resolution": "720p",
            "orientation": "vertical",
            "duration_seconds": 10,
            "prompt": "Test prompt",
            "video_model": "seedance_1_5_pro",
        })

        metadata = manager.create_job(request)
        assert "planner_prompt_hash" in metadata
        assert isinstance(metadata["planner_prompt_hash"], str)
        assert len(metadata["planner_prompt_hash"]) == 12
