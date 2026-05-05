"""Valida o registro de modelos do web studio."""

import sys
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from webapp.model_registry import VIDEO_MODEL_REGISTRY, get_model_config


def main():
    print("=" * 50)
    print("TESTE: Web Model Registry")
    print("=" * 50)

    esperados = {"kling_3_0", "seedance_2_0", "cinema_studio_3_0"}
    presentes = set(VIDEO_MODEL_REGISTRY.keys())

    if presentes != esperados:
        print(f"  ✗ Chaves incorretas: {presentes}")
        return 1

    for key in sorted(esperados):
        config = get_model_config(key)
        print(f"  ✓ {config.label}: {config.application}")
        if config.allowed_resolutions != ("720p", "1080p"):
            print(f"  ✗ {key} tem resoluções inválidas: {config.allowed_resolutions}")
            return 1

    print("-" * 50)
    print("  ✓ TESTE WEB MODEL REGISTRY: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())

