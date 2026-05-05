"""Start, stop and inspect the local José Wipes web studio server."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from scripts.config import LOGS_DIR, OUTPUT_DIR, PROJECT_ROOT


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_TIMEOUT_SECONDS = 20
RUNTIME_DIR = OUTPUT_DIR / "runtime"
DEFAULT_RUNTIME_FILE = RUNTIME_DIR / "web_server.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_path(runtime_file: Path | None = None) -> Path:
    target = Path(runtime_file) if runtime_file else DEFAULT_RUNTIME_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_runtime(runtime_file: Path | None = None) -> dict[str, object]:
    target = _runtime_path(runtime_file)
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def _write_runtime(data: dict[str, object], runtime_file: Path | None = None) -> Path:
    target = _runtime_path(runtime_file)
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

    data = _read_runtime(runtime_file)
    if not data:
        return {}

    data = dict(data)
    data["external_connectivity_checked"] = True
    data["external_connectivity_ok"] = ok
    data["external_connectivity_checked_at"] = _now_iso()
    _write_runtime(data, runtime_file)
    return data


def _http_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _pid_is_running(pid: int | None) -> bool:
    if not pid:
        return False

    if os.name == "nt":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                process_query_limited_information, False, pid
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
            return True
        except Exception:
            return False

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _port_is_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def get_web_server_status(
    *,
    runtime_file: Path | None = None,
    check_http: bool = True,
) -> dict[str, object]:
    """Return the current status of the local web server."""

    data = _read_runtime(runtime_file)
    if not data:
        return {"status": "not_running"}

    pid = int(data.get("pid", 0) or 0)
    url = str(data.get("url", "") or "")
    pid_running = _pid_is_running(pid)
    http_ready = _http_ready(url) if check_http and url else False

    if http_ready:
        status = "ready"
    elif pid_running:
        status = "starting"
    else:
        status = "not_running"

    data = dict(data)
    data["status"] = status
    return data


def start_web_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    runtime_file: Path | None = None,
    log_dir: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    reload: bool = False,
) -> dict[str, object]:
    """Start uvicorn in the background and return once GET / is ready."""

    runtime_target = _runtime_path(runtime_file)
    current_status = get_web_server_status(runtime_file=runtime_target)
    if current_status.get("status") == "ready":
        current_host = str(current_status.get("host", "") or "")
        current_port = int(current_status.get("port", 0) or 0)
        if current_host == host and current_port == port:
            return current_status
        raise RuntimeError(
            f"Já existe um servidor pronto em {current_status.get('url')}. Pare-o antes de subir outro."
        )

    if _port_is_in_use(host, port):
        raise RuntimeError(
            f"A porta {port} já está em uso. Pare o servidor atual ou escolha outra porta."
        )

    logs_target = Path(log_dir) if log_dir else LOGS_DIR
    logs_target.mkdir(parents=True, exist_ok=True)
    stdout_log = logs_target / "webapp.out.log"
    stderr_log = logs_target / "webapp.err.log"

    with open(stdout_log, "ab") as stdout_handle, open(stderr_log, "ab") as stderr_handle:
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "webapp.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ]
        if reload:
            command.append("--reload")

        popen_kwargs: dict[str, object] = {
            "cwd": str(PROJECT_ROOT),
            "stdout": stdout_handle,
            "stderr": stderr_handle,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )
        else:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(command, **popen_kwargs)

    url = f"http://{host}:{port}"
    runtime_payload = {
        "status": "starting",
        "pid": process.pid,
        "host": host,
        "port": port,
        "url": url,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "started_at": _now_iso(),
        "reload": reload,
        "startup_mode": "runner",
        "recommended_start_command": "python -m scripts.web_server start",
        "external_connectivity_checked": False,
    }
    _write_runtime(runtime_payload, runtime_target)

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _http_ready(url):
            runtime_payload["status"] = "ready"
            runtime_payload["ready_at"] = _now_iso()
            _write_runtime(runtime_payload, runtime_target)
            return runtime_payload

        if not _pid_is_running(process.pid):
            break

        time.sleep(0.5)

    try:
        stop_web_server(runtime_file=runtime_target)
    except Exception:
        pass

    raise RuntimeError(
        f"O servidor web não respondeu em até {timeout_seconds}s. Veja {stderr_log}."
    )


def stop_web_server(*, runtime_file: Path | None = None) -> dict[str, object]:
    """Stop the background web server recorded in the runtime file."""

    runtime_target = _runtime_path(runtime_file)
    data = _read_runtime(runtime_target)
    if not data:
        return {"status": "not_running"}

    pid = int(data.get("pid", 0) or 0)
    if not _pid_is_running(pid):
        runtime_target.unlink(missing_ok=True)
        return {"status": "not_running", "pid": pid}

    if os.name == "nt":
        import signal

        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode not in (0, 128):
                raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    else:
        import signal

        os.kill(pid, signal.SIGTERM)

    deadline = time.time() + 10
    while time.time() < deadline:
        if not _pid_is_running(pid):
            runtime_target.unlink(missing_ok=True)
            return {"status": "stopped", "pid": pid}
        time.sleep(0.25)

    raise RuntimeError(f"Não foi possível encerrar o servidor com PID {pid}.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Controle do servidor web local José Wipes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Sobe o servidor web em background")
    start_parser.add_argument("--host", default=DEFAULT_HOST)
    start_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    start_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    start_parser.add_argument("--reload", action="store_true")
    start_parser.add_argument("--runtime-file", type=Path, default=DEFAULT_RUNTIME_FILE)
    start_parser.add_argument("--log-dir", type=Path, default=LOGS_DIR)

    stop_parser = subparsers.add_parser("stop", help="Encerra o servidor web em background")
    stop_parser.add_argument("--runtime-file", type=Path, default=DEFAULT_RUNTIME_FILE)

    status_parser = subparsers.add_parser("status", help="Mostra o status atual do servidor")
    status_parser.add_argument("--runtime-file", type=Path, default=DEFAULT_RUNTIME_FILE)

    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        if args.command == "start":
            result = start_web_server(
                host=args.host,
                port=args.port,
                runtime_file=args.runtime_file,
                log_dir=args.log_dir,
                timeout_seconds=args.timeout,
                reload=args.reload,
            )
        elif args.command == "stop":
            result = stop_web_server(runtime_file=args.runtime_file)
        else:
            result = get_web_server_status(runtime_file=args.runtime_file)

        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
