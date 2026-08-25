"""Guardrails for the EasyPanel GitHub Actions workflow."""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    workflow_path = (
        Path(__file__).parent.parent / ".github" / "workflows" / "easypanel-deploy.yml"
    )
    if not workflow_path.exists():
        print(f"Workflow nao encontrado: {workflow_path}")
        return 1

    content = workflow_path.read_text(encoding="utf-8")
    expected_fragments = [
        "workflow_dispatch:",
        "push:",
        "timeout 20m python -m pytest",
        "curl --fail-with-body",
        "EASYPANEL_DEPLOY_URL",
        "vars.APP_URL",
    ]
    missing = [fragment for fragment in expected_fragments if fragment not in content]
    if missing:
        print(f"Workflow perdeu blocos obrigatorios: {missing}")
        return 1

    if "HOSTINGER_API_KEY" in content or "HOSTINGER_VM_ID" in content:
        print("Workflow ainda depende de configuracao da Hostinger")
        return 1

    print("EasyPanel GitHub Actions: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
