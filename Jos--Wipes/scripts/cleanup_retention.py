"""Cleanup old rendered jobs and log files using age-based retention."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config import LOGS_DIR, OUTPUT_DIR


UTC = timezone.utc
DEFAULT_JOB_DAYS = 30
DEFAULT_LOG_DAYS = 14


@dataclass(frozen=True)
class CleanupCandidate:
    kind: str
    path: Path
    last_activity_at: datetime
    age_days: float


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _from_timestamp(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _job_last_activity(job_dir: Path) -> datetime:
    metadata_path = job_dir / "metadata.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            updated_at = metadata.get("updated_at")
            if isinstance(updated_at, str) and updated_at.strip():
                return _normalize_datetime(datetime.fromisoformat(updated_at))
        except Exception:
            pass
        return _from_timestamp(metadata_path)
    return _from_timestamp(job_dir)


def _age_days(*, now: datetime, timestamp: datetime) -> float:
    return max((now - timestamp).total_seconds(), 0.0) / 86400.0


def discover_expired_jobs(
    jobs_dir: Path,
    *,
    older_than_days: int = DEFAULT_JOB_DAYS,
    now: datetime | None = None,
) -> list[CleanupCandidate]:
    now = _normalize_datetime(now or datetime.now(tz=UTC))
    cutoff = now - timedelta(days=older_than_days)
    candidates: list[CleanupCandidate] = []

    if not jobs_dir.exists():
        return candidates

    for job_dir in sorted(path for path in jobs_dir.iterdir() if path.is_dir()):
        last_activity_at = _job_last_activity(job_dir)
        if last_activity_at <= cutoff:
            candidates.append(
                CleanupCandidate(
                    kind="job",
                    path=job_dir,
                    last_activity_at=last_activity_at,
                    age_days=_age_days(now=now, timestamp=last_activity_at),
                )
            )

    return candidates


def discover_expired_logs(
    logs_dir: Path,
    *,
    older_than_days: int = DEFAULT_LOG_DAYS,
    now: datetime | None = None,
) -> list[CleanupCandidate]:
    now = _normalize_datetime(now or datetime.now(tz=UTC))
    cutoff = now - timedelta(days=older_than_days)
    candidates: list[CleanupCandidate] = []

    if not logs_dir.exists():
        return candidates

    for log_path in sorted(path for path in logs_dir.iterdir() if path.is_file()):
        last_activity_at = _from_timestamp(log_path)
        if last_activity_at <= cutoff:
            candidates.append(
                CleanupCandidate(
                    kind="log",
                    path=log_path,
                    last_activity_at=last_activity_at,
                    age_days=_age_days(now=now, timestamp=last_activity_at),
                )
            )

    return candidates


def collect_candidates(
    *,
    jobs_dir: Path,
    logs_dir: Path,
    job_days: int = DEFAULT_JOB_DAYS,
    log_days: int = DEFAULT_LOG_DAYS,
    now: datetime | None = None,
) -> list[CleanupCandidate]:
    now = _normalize_datetime(now or datetime.now(tz=UTC))
    return [
        *discover_expired_jobs(jobs_dir, older_than_days=job_days, now=now),
        *discover_expired_logs(logs_dir, older_than_days=log_days, now=now),
    ]


def _ensure_within_root(path: Path, root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError(f"Refusing to delete outside root: {resolved_path}")


def delete_candidates(
    candidates: list[CleanupCandidate],
    *,
    jobs_dir: Path,
    logs_dir: Path,
) -> list[Path]:
    deleted: list[Path] = []

    for candidate in candidates:
        root = jobs_dir if candidate.kind == "job" else logs_dir
        _ensure_within_root(candidate.path, root)

        if candidate.kind == "job":
            shutil.rmtree(candidate.path)
        else:
            candidate.path.unlink(missing_ok=True)
        deleted.append(candidate.path)

    return deleted


def _format_candidate(candidate: CleanupCandidate) -> str:
    stamp = candidate.last_activity_at.astimezone(UTC).isoformat()
    return (
        f"[{candidate.kind}] {candidate.path} | "
        f"last_activity={stamp} | age_days={candidate.age_days:.1f}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clean old Jose Wipes jobs and log files using retention windows."
    )
    parser.add_argument(
        "--jobs-dir",
        type=Path,
        default=OUTPUT_DIR / "web_jobs",
        help="Directory containing persisted web jobs.",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=LOGS_DIR,
        help="Directory containing application logs.",
    )
    parser.add_argument(
        "--job-days",
        type=int,
        default=DEFAULT_JOB_DAYS,
        help="Delete jobs whose last activity is older than this many days.",
    )
    parser.add_argument(
        "--log-days",
        type=int,
        default=DEFAULT_LOG_DAYS,
        help="Delete log files older than this many days.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete the selected files. Default mode is dry-run.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    candidates = collect_candidates(
        jobs_dir=args.jobs_dir,
        logs_dir=args.logs_dir,
        job_days=args.job_days,
        log_days=args.log_days,
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print("=" * 60)
    print(f"RETENTION CLEANUP ({mode})")
    print("=" * 60)
    print(f"Jobs dir: {args.jobs_dir}")
    print(f"Logs dir: {args.logs_dir}")
    print(f"Job retention: {args.job_days} days")
    print(f"Log retention: {args.log_days} days")
    print("-" * 60)

    if not candidates:
        print("No expired jobs or logs found.")
        return 0

    for candidate in candidates:
        print(_format_candidate(candidate))

    print("-" * 60)
    print(f"Candidates: {len(candidates)}")

    if not args.apply:
        print("Dry-run only. Re-run with --apply to delete the paths above.")
        return 0

    deleted = delete_candidates(
        candidates,
        jobs_dir=args.jobs_dir,
        logs_dir=args.logs_dir,
    )
    print(f"Deleted: {len(deleted)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
