"""Guardrails for the optional Hostinger GitHub Actions workflow."""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> int:
    print("=" * 50)
    print("TESTE: Hostinger GitHub Actions")
    print("=" * 50)

    workflow_path = (
        Path(__file__).parent.parent / ".github" / "workflows" / "hostinger-deploy.yml"
    )
    if not workflow_path.exists():
        print(f"  x Workflow nao encontrado: {workflow_path}")
        return 1

    content = workflow_path.read_text(encoding="utf-8")

    expected_fragments = [
        "workflow_dispatch:",
        "push:",
        "uses: hostinger/deploy-action@v1",
        "docker-compose-path: docker-compose.hostinger.yml",
        "project-name: jose-wipes-studio",
        "HOSTINGER_API_KEY",
        "HOSTINGER_VM_ID",
        "TRAEFIK_BASIC_AUTH_USERS",
        "if: steps.preflight.outputs.configured == 'true'",
    ]
    missing = [fragment for fragment in expected_fragments if fragment not in content]
    if missing:
        print(f"  x Workflow perdeu blocos obrigatorios: {missing}")
        return 1

    if "Hostinger deployment skipped because HOSTINGER_API_KEY or HOSTINGER_VM_ID is missing." not in content:
        print("  x Workflow deveria pular sem falhar quando a configuracao nao existir")
        return 1

    print("  + Workflow suporta deploy manual e automatico")
    print("  + Deploy usa docker-compose.hostinger.yml e preflight seguro")
    print("-" * 50)
    print("  + TESTE HOSTINGER GITHUB ACTIONS: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
