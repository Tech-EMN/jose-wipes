"""Validate retention cleanup helpers for Hostinger operations."""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.cleanup_retention import collect_candidates, delete_candidates


UTC = timezone.utc


def _touch_with_age(path: Path, *, days_old: int) -> None:
    target_time = (datetime.now(tz=UTC) - timedelta(days=days_old)).timestamp()
    os.utime(path, (target_time, target_time))


def _write_job(job_dir: Path, *, updated_at: datetime) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    metadata = {"updated_at": updated_at.isoformat()}
    (job_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def main() -> int:
    print("=" * 50)
    print("TESTE: Cleanup Retention")
    print("=" * 50)

    temp_dir = Path(__file__).parent.parent / "output" / "test_cleanup_retention"
    jobs_dir = temp_dir / "web_jobs"
    logs_dir = temp_dir / "logs"
    now = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)

    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    try:
        old_job_dir = jobs_dir / "old-job"
        new_job_dir = jobs_dir / "new-job"
        _write_job(old_job_dir, updated_at=now - timedelta(days=45))
        _write_job(new_job_dir, updated_at=now - timedelta(days=2))

        old_log = logs_dir / "old.log"
        new_log = logs_dir / "new.log"
        old_log.write_text("old log", encoding="utf-8")
        new_log.write_text("new log", encoding="utf-8")
        _touch_with_age(old_log, days_old=20)
        _touch_with_age(new_log, days_old=1)

        candidates = collect_candidates(
            jobs_dir=jobs_dir,
            logs_dir=logs_dir,
            job_days=30,
            log_days=14,
            now=now,
        )

        candidate_paths = {candidate.path.name for candidate in candidates}
        if candidate_paths != {"old-job", "old.log"}:
            print(f"  x Selecionou candidatos errados: {candidate_paths}")
            return 1

        if not old_job_dir.exists() or not old_log.exists():
            print("  x Dry-run nao deveria apagar nada")
            return 1

        deleted = delete_candidates(candidates, jobs_dir=jobs_dir, logs_dir=logs_dir)
        deleted_names = {path.name for path in deleted}
        if deleted_names != {"old-job", "old.log"}:
            print(f"  x Delete reportou caminhos errados: {deleted_names}")
            return 1

        if old_job_dir.exists() or old_log.exists():
            print("  x Cleanup nao apagou os artefatos expirados")
            return 1

        if not new_job_dir.exists() or not new_log.exists():
            print("  x Cleanup removeu artefatos recentes por engano")
            return 1

        print("  + Dry-run identifica somente jobs/logs expirados")
        print("  + Apply remove apenas os caminhos antigos")
        print("-" * 50)
        print("  + TESTE CLEANUP RETENTION: PASSOU")
        return 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
