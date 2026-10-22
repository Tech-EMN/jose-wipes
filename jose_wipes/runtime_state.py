"""Runtime state file shared by the local server runner and the web app."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from jose_wipes.config import OUTPUT_DIR


RUNTIME_DIR = OUTPUT_DIR / "runtime"
DEFAULT_RUNTIME_FILE = RUNTIME_DIR / "web_server.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_path(runtime_file: Path | None = None) -> Path:
    target = Path(runtime_file) if runtime_file else DEFAULT_RUNTIME_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def read_runtime(runtime_file: Path | None = None) -> dict[str, object]:
    target = runtime_path(runtime_file)
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def write_runtime(data: dict[str, object], runtime_file: Path | None = None) -> Path:
    target = runtime_path(runtime_file)
    temp_path = target.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(target)
    return target


def mark_external_connectivity_checked(
    *,
    runtime_file: Path | None = None,
    ok: bool,
) -> dict[str, object]:
    """Persist that this server instance has passed an external connectivity probe."""

    data = read_runtime(runtime_file)
    if not data:
        return {}

    data = dict(data)
    data["external_connectivity_checked"] = True
    data["external_connectivity_ok"] = ok
    data["external_connectivity_checked_at"] = now_iso()
    write_runtime(data, runtime_file)
    return data
