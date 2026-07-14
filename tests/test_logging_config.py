"""Tests for F13: structured logging configuration."""

from __future__ import annotations

import json
import logging
import pytest
from pathlib import Path

from scripts.logging_config import (
    JsonFormatter,
    PlainFormatter,
    JobLogAdapter,
    configure_logging,
    get_logger,
)


class TestJsonFormatter:
    def test_format_produces_valid_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=42, msg="Hello %s", args=("world",), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert "world" in parsed["message"]

    def test_format_includes_timestamp(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="test", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "timestamp" in parsed
        assert "T" in parsed["timestamp"]  # ISO 8601

    def test_format_includes_module_and_line(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="app.py",
            lineno=99, msg="Warning!", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["module"] == "app"
        assert parsed["line"] == 99

    def test_format_includes_job_id_if_set(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="Job started", args=(), exc_info=None,
        )
        record.job_id = "abc123"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["job_id"] == "abc123"


class TestJobLogAdapter:
    def test_adapter_injects_job_id(self, caplog):
        logger = logging.getLogger("test_adapter")
        logger.setLevel(logging.INFO)
        adapter = JobLogAdapter(logger, job_id="job-42")

        with caplog.at_level(logging.INFO):
            adapter.info("Processing started")

        assert len(caplog.records) == 1
        assert caplog.records[0].job_id == "job-42"

    def test_adapter_without_job_id(self, caplog):
        logger = logging.getLogger("test_adapter_none")
        logger.setLevel(logging.INFO)
        adapter = JobLogAdapter(logger, job_id=None)

        with caplog.at_level(logging.INFO):
            adapter.info("No job context")

        assert caplog.records[0].job_id is None


class TestConfigureLogging:
    def test_configure_with_defaults(self):
        configure_logging(level="WARNING")
        root = logging.getLogger()
        assert len(root.handlers) >= 1

    def test_configure_json_mode(self):
        configure_logging(level="INFO", json_output=True)
        root = logging.getLogger()
        handler = root.handlers[0]
        assert isinstance(handler.formatter, JsonFormatter)

    def test_configure_plain_mode(self):
        configure_logging(level="INFO", json_output=False)
        root = logging.getLogger()
        handler = root.handlers[0]
        assert isinstance(handler.formatter, PlainFormatter)

    def test_configure_with_log_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        configure_logging(level="INFO", json_output=True, log_dir=log_dir)
        assert log_dir.exists()
        # File handler should exist
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) >= 1


class TestGetLogger:
    def test_returns_plain_logger(self):
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)

    def test_returns_adapter_with_job_id(self):
        logger = get_logger("test.job", job_id="xyz")
        assert isinstance(logger, JobLogAdapter)
        assert logger.job_id == "xyz"
