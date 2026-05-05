"""Verifica se FFmpeg está instalado e mostra a versão."""

import subprocess
import sys


def main():
    print("=" * 50)
    print("TESTE: FFmpeg")
    print("=" * 50)

    for cmd in ["ffmpeg", "ffprobe"]:
        try:
            result = subprocess.run(
                [cmd, "-version"],
                capture_output=True, text=True, timeout=10
            )
            versao = result.stdout.split("\n")[0]
            print(f"  ✓ {cmd}: {versao}")
        except FileNotFoundError:
            print(f"  ✗ {cmd} NÃO encontrado. Instale FFmpeg: https://ffmpeg.org/download.html")
            sys.exit(1)
        except Exception as e:
            print(f"  ✗ Erro ao verificar {cmd}: {e}")
            sys.exit(1)

    print("-" * 50)
    print("  ✓ FFmpeg está instalado e funcionando!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
