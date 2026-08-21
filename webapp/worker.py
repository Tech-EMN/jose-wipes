"""Worker entrypoint for the José Wipes background job processor.

Runs as a separate container — polls the shared output volume for
new jobs and processes them one at a time. Designed to be the CMD
for the jose-wipes-worker Docker service.

Usage:
    python -m webapp.worker
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

# Ensure project root is in path
_project_root = Path(__file__).parent.parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.config import OUTPUT_DIR, LOGS_DIR, OPENAI_PLANNER_MODEL
from webapp.job_manager import FilePollingJobManager

_log = logging.getLogger("jose-wipes-worker")

POLL_INTERVAL_SECONDS = int(os.getenv("JW_WORKER_POLL_INTERVAL", "2"))
SHUTDOWN_GRACE_SECONDS = int(os.getenv("JW_WORKER_GRACE", "30"))
CLEANUP_INTERVAL_HOURS = int(os.getenv("JW_CLEANUP_INTERVAL_HOURS", "6"))
CLEANUP_JOB_DAYS = int(os.getenv("JW_CLEANUP_JOB_DAYS", "30"))
CLEANUP_LOG_DAYS = int(os.getenv("JW_CLEANUP_LOG_DAYS", "14"))


def start_cleanup_scheduler(jobs_dir: Path) -> None:
    """Start a background thread that runs retention cleanup periodically.

    Replaces the need for a manual cleanup script — the worker
    automatically removes expired jobs and logs.
    """
    import logging
    _log = logging.getLogger("jose-wipes-cleanup")

    def _cleanup_loop():
        import time as _time
        from scripts.cleanup_retention import (
            collect_candidates,
            delete_candidates,
            DEFAULT_JOB_DAYS,
            DEFAULT_LOG_DAYS,
        )

        while True:
            _time.sleep(CLEANUP_INTERVAL_HOURS * 3600)
            try:
                candidates = collect_candidates(
                    jobs_dir=jobs_dir,
                    logs_dir=LOGS_DIR,
                    job_days=CLEANUP_JOB_DAYS,
                    log_days=CLEANUP_LOG_DAYS,
                )
                if candidates:
                    _log.info("Cleanup: found %d expired items", len(candidates))
                    deleted = delete_candidates(
                        candidates,
                        jobs_dir=jobs_dir,
                        logs_dir=LOGS_DIR,
                    )
                    _log.info("Cleanup: removed %d items", len(deleted))
                else:
                    _log.debug("Cleanup: no expired items found")
            except Exception:
                _log.exception("Cleanup iteration failed")

    cleanup_thread = threading.Thread(
        target=_cleanup_loop,
        name="jose-wipes-cleanup",
        daemon=True,
    )
    cleanup_thread.start()
    _log.info(
        "Cleanup scheduler started (interval=%dh, job_retention=%dd, log_retention=%dd)",
        CLEANUP_INTERVAL_HOURS, CLEANUP_JOB_DAYS, CLEANUP_LOG_DAYS,
    )


def main() -> int:
    """Start the file-polling worker and run until SIGTERM/SIGINT."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    _log.info("José Wipes Worker starting (poll interval=%ds, grace=%ds)",
              POLL_INTERVAL_SECONDS, SHUTDOWN_GRACE_SECONDS)
    _log.info("Planner model: %s", OPENAI_PLANNER_MODEL)

    jobs_dir = OUTPUT_DIR / "web_jobs"
    manager = FilePollingJobManager(
        jobs_dir=jobs_dir,
        poll_interval=POLL_INTERVAL_SECONDS,
    )

    shutdown_requested = threading.Event()

    def _handle_signal(signum, frame):
        _log.info("Received signal %d, shutting down gracefully...", signum)
        shutdown_requested.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Start periodic cleanup (runs every 6h via background thread)
    start_cleanup_scheduler(jobs_dir)

    try:
        manager.start()
        shutdown_requested.wait()
    except KeyboardInterrupt:
        _log.info("Worker interrupted")
    except Exception:
        _log.exception("Worker crashed")
        return 1
    finally:
        manager.stop()

    _log.info("Worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
