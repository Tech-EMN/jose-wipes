"""Per-job record of render stage outcomes, used to resume from the failed stage."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from jose_wipes.integrations.errors import IntegrationFailure

RENDER_STAGES_FILENAME = "etapas_render.json"

_log = logging.getLogger(__name__)


class RenderStage(str, Enum):
    PLAN = "plan"
    GENERATE_MEDIA = "generate_media"
    COMPOSE = "compose"
    PUBLISH = "publish"


class StageStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


STAGE_ORDER = tuple(RenderStage)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pending() -> dict[str, object]:
    return {"status": StageStatus.PENDING.value}


class RenderCheckpoints:
    """Stores the status and output of each stage in the job folder."""

    def __init__(self, job_dir: Path) -> None:
        self._path = job_dir / RENDER_STAGES_FILENAME
        self._stages = self._load()
        self._save()

    def output(self, stage: RenderStage) -> dict[str, object] | None:
        entry = self._stages[stage.value]
        if entry.get("status") != StageStatus.COMPLETED.value:
            return None
        output = entry.get("output")
        return output if isinstance(output, dict) else None

    def restart_from(self, stage: RenderStage) -> None:
        for later in STAGE_ORDER[STAGE_ORDER.index(stage):]:
            self._stages[later.value] = _pending()
        self._save()

    def completed(self, stage: RenderStage, output: dict[str, object] | None = None) -> None:
        entry: dict[str, object] = {"status": StageStatus.COMPLETED.value, "finished_at": _now_iso()}
        if output is not None:
            entry["output"] = output
        self._stages[stage.value] = entry
        self._save()

    def failed(self, stage: RenderStage, failure: IntegrationFailure) -> None:
        self._stages[stage.value] = {
            "status": StageStatus.FAILED.value,
            "finished_at": _now_iso(),
            "failure_code": failure.code,
            "failed_service": failure.service,
            "retryable": failure.retryable,
        }
        self._save()

    def _load(self) -> dict[str, dict[str, object]]:
        fresh = {stage.value: _pending() for stage in RenderStage}
        if not self._path.exists():
            return fresh
        try:
            stored = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _log.warning("Unreadable render checkpoints at %s; starting from scratch", self._path, exc_info=True)
            return fresh
        if not isinstance(stored, dict):
            return fresh
        return {
            name: entry if isinstance(entry := stored.get(name), dict) else _pending()
            for name in fresh
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(self._stages, indent=2, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(self._path)
