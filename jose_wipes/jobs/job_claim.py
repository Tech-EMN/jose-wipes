"""Exclusive job ownership on the shared jobs volume.

A worker owns a job by atomically creating ``.claim`` inside the job
directory and keeps the claim alive by touching it while it processes
the job. A claim that stops being touched marks the job as abandoned.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType

CLAIM_FILE_NAME = ".claim"
DEFAULT_HEARTBEAT_SECONDS = int(os.getenv("JW_JOB_HEARTBEAT_SECONDS", "30"))
DEFAULT_STALE_AFTER_SECONDS = int(os.getenv("JW_JOB_STALE_SECONDS", "300"))

_log = logging.getLogger(__name__)


def claim_path(job_dir: Path) -> Path:
    return job_dir / CLAIM_FILE_NAME


def try_claim(job_dir: Path) -> bool:
    try:
        descriptor = os.open(claim_path(job_dir), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False

    owner = {
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "claimed_at": datetime.now(timezone.utc).isoformat(),
    }
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(owner, handle)
    return True


def release_claim(job_dir: Path) -> None:
    claim_path(job_dir).unlink(missing_ok=True)


def is_claimed(job_dir: Path) -> bool:
    return claim_path(job_dir).exists()


def claim_age_seconds(job_dir: Path, now: float | None = None) -> float | None:
    try:
        touched_at = claim_path(job_dir).stat().st_mtime
    except FileNotFoundError:
        return None
    reference = time.time() if now is None else now
    return reference - touched_at


class ClaimHeartbeat:
    def __init__(self, job_dir: Path, interval_seconds: float = DEFAULT_HEARTBEAT_SECONDS) -> None:
        self._path = claim_path(job_dir)
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> ClaimHeartbeat:
        self._thread = threading.Thread(
            target=self._beat,
            name=f"jose-wipes-claim-{self._path.parent.name}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval_seconds + 1)

    def _beat(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            try:
                os.utime(self._path)
            except OSError:
                _log.warning("Could not refresh claim %s", self._path, exc_info=True)
