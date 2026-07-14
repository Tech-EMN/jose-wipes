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
import time
from pathlib import Path

# Ensure project root is in path
_project_root = Path(__file__).parent.parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.config import OUTPUT_DIR
from webapp.job_manager import FilePollingJobManager

_log = logging.getLogger("jose-wipes-worker")

POLL_INTERVAL_SECONDS = int(os.getenv("JW_WORKER_POLL_INTERVAL", "2"))
SHUTDOWN_GRACE_SECONDS = int(os.getenv("JW_WORKER_GRACE", "30"))


def main() -> int:
    """Start the file-polling worker and run until SIGTERM/SIGINT."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    _log.info("José Wipes Worker starting (poll interval=%ds, grace=%ds)",
              POLL_INTERVAL_SECONDS, SHUTDOWN_GRACE_SECONDS)

    jobs_dir = OUTPUT_DIR / "web_jobs"
    manager = FilePollingJobManager(
        jobs_dir=jobs_dir,
        poll_interval=POLL_INTERVAL_SECONDS,
    )

    shutdown_requested = threading.Event() if "threading" in sys.modules else None

    def _handle_signal(signum, frame):
        _log.info("Received signal %d, shutting down gracefully...", signum)
        manager.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        manager.start()
        # start() blocks until stop() is called
    except KeyboardInterrupt:
        _log.info("Worker interrupted")
    except Exception:
        _log.exception("Worker crashed")
        return 1

    _log.info("Worker stopped")
    return 0


if __name__ == "__main__":
    import threading  # for signal handling
    sys.exit(main())
