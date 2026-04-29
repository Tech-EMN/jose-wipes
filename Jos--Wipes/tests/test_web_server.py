"""Valida o runner de start/stop/status do servidor web local."""

import shutil
import socket
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.web_server import (
    get_web_server_status,
    mark_external_connectivity_checked,
    start_web_server,
    stop_web_server,
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main():
    print("=" * 50)
    print("TESTE: Web Server Runner")
    print("=" * 50)

    temp_dir = Path(__file__).parent.parent / "output" / "test_web_server"
    runtime_file = temp_dir / "runtime" / "web_server.json"
    log_dir = temp_dir / "logs"
    port = _find_free_port()

    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        started = start_web_server(
            host="127.0.0.1",
            port=port,
            runtime_file=runtime_file,
            log_dir=log_dir,
            timeout_seconds=20,
            reload=False,
        )
        if started.get("status") != "ready":
            print(f"  x Servidor nao ficou pronto: {started}")
            return 1

        status = get_web_server_status(runtime_file=runtime_file)
        if status.get("status") != "ready":
            print(f"  x Status deveria ser ready: {status}")
            return 1
        if status.get("startup_mode") != "runner":
            print(f"  x Startup mode deveria ser runner: {status}")
            return 1
        if status.get("external_connectivity_checked") is not False:
            print(f"  x Connectivity checked deveria iniciar como False: {status}")
            return 1

        marked = mark_external_connectivity_checked(runtime_file=runtime_file, ok=True)
        if marked.get("external_connectivity_checked") is not True:
            print(f"  x Runtime deveria marcar connectivity checked: {marked}")
            return 1
        if marked.get("external_connectivity_ok") is not True:
            print(f"  x Runtime deveria marcar connectivity ok: {marked}")
            return 1

        started_at = time.time()
        with urllib.request.urlopen(started["url"], timeout=5) as response:
            if response.status != 200:
                print(f"  x GET / retornou {response.status}")
                return 1
        elapsed = time.time() - started_at
        if elapsed > 5:
            print(f"  x GET / demorou demais apos startup: {elapsed:.1f}s")
            return 1

        stopped = stop_web_server(runtime_file=runtime_file)
        if stopped.get("status") != "stopped":
            print(f"  x Stop nao encerrou o processo: {stopped}")
            return 1

        final_status = get_web_server_status(runtime_file=runtime_file, check_http=False)
        if final_status.get("status") != "not_running":
            print(f"  x Status final deveria ser not_running: {final_status}")
            return 1

        print("  + Start/stop/status devolvem link, PID e encerram limpo")
        print("  + Runtime persiste startup_mode e external_connectivity_checked")
        print("-" * 50)
        print("  + TESTE WEB SERVER RUNNER: PASSOU")
        return 0
    finally:
        try:
            stop_web_server(runtime_file=runtime_file)
        except Exception:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
