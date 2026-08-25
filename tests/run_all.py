"""Executa todos os testes do projeto em ordem e mostra resumo."""

import sys
import subprocess
import time
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path

TESTS_DIR = Path(__file__).parent
PROJECT_ROOT = TESTS_DIR.parent

TESTES = [
    ("FFmpeg", "test_ffmpeg.py"),
    ("Higgsfield Image", "test_higgsfield_image.py"),
    ("Higgsfield Video", "test_higgsfield_video.py"),
    ("ElevenLabs", "test_elevenlabs.py"),
    ("Google Drive", "test_gdrive.py"),
    ("Claude Decomposição", "test_claude_decomposicao.py"),
    ("FFmpeg Composição", "test_ffmpeg_composicao.py"),
    ("Brandbook", "test_brandbook.py"),
    ("Prompts Library", "test_prompts_library.py"),
    ("Vozes", "test_vozes.py"),
    ("System Prompt", "test_system_prompt.py"),
    ("Pipeline", "test_pipeline.py"),
    ("Product Reference Policy", "test_product_reference.py"),
    ("Product Reference Integration", "test_referencia_produto.py"),
    ("Web Model Registry", "test_web_model_registry.py"),
    ("Web PDF Utils", "test_web_pdf_utils.py"),
    ("Web Planner", "test_web_planner.py"),
    ("Web Job Manager", "test_web_job_manager.py"),
    ("Web Compositor", "test_web_compositor.py"),
    ("Web App", "test_web_app.py"),
    ("Web Server Runner", "test_web_server.py"),
    ("Hostinger Compose", "test_hostinger_compose.py"),
    ("EasyPanel GitHub Actions", "test_easypanel_github_actions.py"),
    ("Cleanup Retention", "test_cleanup_retention.py"),
]


def main():
    print("=" * 60)
    print("BATERIA DE TESTES — José Wipes Pipeline")
    print("=" * 60)

    resultados = []

    for i, (nome, arquivo) in enumerate(TESTES, 1):
        test_path = TESTS_DIR / arquivo
        if not test_path.exists():
            print(f"\n[{i}/{len(TESTES)}] {nome}: PULADO (arquivo não existe)")
            resultados.append((nome, "PULADO"))
            continue

        print(f"\n[{i}/{len(TESTES)}] {nome}...")
        try:
            result = subprocess.run(
                [sys.executable, str(test_path)],
                capture_output=True, text=True, timeout=300,
                cwd=str(PROJECT_ROOT),
                encoding="utf-8", errors="replace"
            )
            if result.returncode == 0:
                resultados.append((nome, "PASSOU"))
                print(f"  ✓ PASSOU")
            else:
                resultados.append((nome, "FALHOU"))
                print(f"  ✗ FALHOU")
                # Mostrar últimas linhas do erro
                output = (result.stdout + result.stderr).strip()
                for line in output.split("\n")[-3:]:
                    print(f"    {line}")
        except subprocess.TimeoutExpired:
            resultados.append((nome, "TIMEOUT"))
            print(f"  ✗ TIMEOUT (>5min)")
        except Exception as e:
            resultados.append((nome, "ERRO"))
            print(f"  ✗ ERRO: {e}")

    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)

    passou = sum(1 for _, s in resultados if s == "PASSOU")
    falhou = sum(1 for _, s in resultados if s == "FALHOU")
    pulou = sum(1 for _, s in resultados if s == "PULADO")
    total = len(resultados)

    for nome, status in resultados:
        icon = {"PASSOU": "✓", "FALHOU": "✗", "PULADO": "⬜", "TIMEOUT": "⏱", "ERRO": "✗"}.get(status, "?")
        print(f"  {icon} {nome}: {status}")

    print("-" * 60)
    print(f"  Total: {total} | Passou: {passou} | Falhou: {falhou} | Pulou: {pulou}")

    return 0 if falhou == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
