"""Structured logging configuration for the José Wipes pipeline.

Provides:
- JSON-formatted log output for machine parsing
- RotatingFileHandler for log persistence
- Job ID injection via logging adapter
- Consistent timestamp format (ISO 8601)

Usage:
    from scripts.logging_config import configure_logging, get_logger

    configure_logging(level="INFO")
    _log = get_logger(__name__, job_id="abc123")
    _log.info("Processing started")
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


class JsonFormatter(logging.Formatter):
    """Emit log records as JSON lines for structured log ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        # Inject extra fields set via adapter
        if hasattr(record, "job_id"):
            payload["job_id"] = record.job_id

        if record.exc_info and record.exc_info[1]:
            payload["exception"] = str(record.exc_info[1])

        return json.dumps(payload, ensure_ascii=False, default=str)


class JobLogAdapter(logging.LoggerAdapter):
    """LoggerAdapter that injects job_id into every log record."""

    def __init__(self, logger: logging.Logger, job_id: str | None = None):
        super().__init__(logger, {})
        self.job_id = job_id

    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})
        extra["job_id"] = self.job_id
        kwargs["extra"] = extra
        return msg, kwargs


class PlainFormatter(logging.Formatter):
    """Human-readable formatter for development (non-JSON mode)."""

    def format(self, record: logging.LogRecord) -> str:
        job_id = getattr(record, "job_id", None)
        prefix = f"[{job_id}] " if job_id else ""
        return (
            f"{self.formatTime(record)} "
            f"{record.levelname:<7} "
            f"{prefix}"
            f"{record.getMessage()}"
        )


def configure_logging(
    *,
    level: str = "INFO",
    json_output: bool | None = None,
    log_dir: Path | None = None,
) -> None:
    """Configure root logger with structured output.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        json_output: If True, use JSON format. If None, auto-detect (JSON in prod).
        log_dir: Directory for rotating log files. If None, disable file logging.
    """
    # Auto-detect JSON mode: JSON when not a TTY (container/production)
    if json_output is None:
        json_output = not sys.stderr.isatty()

    formatter = JsonFormatter() if json_output else PlainFormatter()

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.setLevel(getattr(logging, level.upper(), logging.INFO))

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(console)

    # File handler with rotation
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "openai._base_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str, job_id: str | None = None) -> logging.Logger | JobLogAdapter:
    """Get a logger, optionally with job_id injection.

    Args:
        name: Logger name (usually __name__).
        job_id: If provided, injects job_id into all log records.

    Returns a JobLogAdapter when job_id is provided, otherwise a plain Logger.
    """
    logger = logging.getLogger(name)
    if job_id:
        return JobLogAdapter(logger, job_id=job_id)
    return logger
