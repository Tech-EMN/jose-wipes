"""Tests for F16: upload reference image with exponential backoff retry."""

from __future__ import annotations

import sys
import pytest
from unittest.mock import patch, MagicMock, call


@pytest.fixture(autouse=True)
def _mock_higgsfield_module():
    """Ensure higgsfield_client is always mockable."""
    if "higgsfield_client" not in sys.modules:
        sys.modules["higgsfield_client"] = MagicMock()


class TestUploadReferenceImageRetry:
    """Tests for _upload_reference_image retry behavior."""

    def test_none_path_returns_none(self):
        """None path should return None without calling upload."""
        from webapp.pipeline_service import _upload_reference_image
        assert _upload_reference_image(None) is None

    def test_nonexistent_path_returns_none(self, tmp_path):
        """Non-existent file should return None immediately."""
        from webapp.pipeline_service import _upload_reference_image
        fake_path = tmp_path / "nonexistent.png"
        assert _upload_reference_image(fake_path) is None

    def test_success_on_first_attempt(self, tmp_path):
        """Successful upload should return URL on first attempt."""
        from webapp.pipeline_service import _upload_reference_image

        test_file = tmp_path / "test.png"
        test_file.write_text("fake image data")

        with patch(
            "webapp.pipeline_service.upload_higgsfield_file",
            return_value="https://cdn.example.com/img.png",
        ), patch("time.sleep") as mock_sleep:
            result = _upload_reference_image(str(test_file))
            assert result == "https://cdn.example.com/img.png"
            mock_sleep.assert_not_called()

    def test_retry_on_failure_then_success(self, tmp_path):
        """Should retry on failure and succeed on subsequent attempt."""
        from webapp.pipeline_service import _upload_reference_image

        test_file = tmp_path / "test.png"
        test_file.write_text("fake image data")

        call_count = [0]

        def mock_upload(path_str):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError(f"Timeout attempt {call_count[0]}")
            return "https://cdn.example.com/retry_success.png"

        with patch("webapp.pipeline_service.upload_higgsfield_file", side_effect=mock_upload), patch("time.sleep") as mock_sleep:
            result = _upload_reference_image(str(test_file))
            assert result == "https://cdn.example.com/retry_success.png"
            assert call_count[0] == 3
            assert mock_sleep.call_count == 2
            mock_sleep.assert_has_calls([call(2.0), call(4.0)])

    def test_returns_none_after_all_retries_exhausted(self, tmp_path):
        """Should return None after max retries all fail."""
        from webapp.pipeline_service import _upload_reference_image

        test_file = tmp_path / "test.png"
        test_file.write_text("fake image data")

        call_count = [0]

        def mock_upload(path_str):
            call_count[0] += 1
            raise ConnectionError(f"Always fails {call_count[0]}")

        with patch("webapp.pipeline_service.upload_higgsfield_file", side_effect=mock_upload), patch("time.sleep"):
            result = _upload_reference_image(str(test_file))
            assert result is None
            assert call_count[0] == 3

    def test_backoff_is_exponential(self, tmp_path):
        """Backoff should be exponential: 2s, 4s."""
        from webapp.pipeline_service import _upload_reference_image

        test_file = tmp_path / "test.png"
        test_file.write_text("fake image data")

        call_count = [0]

        def mock_upload(path_str):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError(f"Fail {call_count[0]}")
            return "https://cdn.example.com/ok.png"

        with patch("webapp.pipeline_service.upload_higgsfield_file", side_effect=mock_upload), patch("time.sleep") as mock_sleep:
            _upload_reference_image(str(test_file))
            expected_delays = [2.0, 4.0]  # 2 attempts fail, then success
            actual_delays = [c[0][0] for c in mock_sleep.call_args_list]
            assert actual_delays == expected_delays, f"Expected {expected_delays}, got {actual_delays}"

    def test_max_attempts_is_3(self, tmp_path):
        """After 3 failures, function should stop retrying."""
        from webapp.pipeline_service import _upload_reference_image

        test_file = tmp_path / "test.png"
        test_file.write_text("fake image data")

        call_count = [0]

        def mock_upload(path_str):
            call_count[0] += 1
            raise ConnectionError("Network error")

        with patch("webapp.pipeline_service.upload_higgsfield_file", side_effect=mock_upload), patch("time.sleep"):
            result = _upload_reference_image(str(test_file))
            assert result is None
            assert call_count[0] == 3
