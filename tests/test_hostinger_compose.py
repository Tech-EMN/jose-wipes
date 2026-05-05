"""Guardrails for the Hostinger production compose file."""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> int:
    print("=" * 50)
    print("TESTE: Hostinger Compose")
    print("=" * 50)

    compose_path = Path(__file__).parent.parent / "docker-compose.hostinger.yml"
    if not compose_path.exists():
        print(f"  x Compose nao encontrado: {compose_path}")
        return 1

    content = compose_path.read_text(encoding="utf-8")

    expected_fragments = [
        "restart: unless-stopped",
        "traefik-proxy",
        "traefik.enable=true",
        "traefik.http.middlewares.jose-wipes-auth.basicauth.users=",
        "jose_wipes_output:/app/output",
        "jose_wipes_logs:/app/logs",
        "PYTHONUNBUFFERED: ${PYTHONUNBUFFERED:-1}",
        "TZ: ${TZ:-America/Sao_Paulo}",
        "PORT: \"8000\"",
    ]
    missing = [fragment for fragment in expected_fragments if fragment not in content]
    if missing:
        print(f"  x Compose perdeu blocos obrigatorios: {missing}")
        return 1

    forbidden_fragments = [
        "\n    ports:",
        "/app/assets",
    ]
    found_forbidden = [fragment for fragment in forbidden_fragments if fragment in content]
    if found_forbidden:
        print(f"  x Compose contem blocos proibidos: {found_forbidden}")
        return 1

    print("  + Compose usa Traefik, volumes persistentes e sem publicar 8000")
    print("  + Assets nao sao montados como volume")
    print("-" * 50)
    print("  + TESTE HOSTINGER COMPOSE: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
