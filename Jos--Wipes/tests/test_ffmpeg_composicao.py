"""Testa composição de vídeo com FFmpeg (gera vídeos sintéticos e concatena)."""

import sys
import subprocess
import json
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from scripts.config import OUTPUT_DIR


def main():
    print("=" * 50)
    print("TESTE: FFmpeg — Composição de Vídeo")
    print("=" * 50)

    cena1 = OUTPUT_DIR / "cenas" / "teste_cena1.mp4"
    cena2 = OUTPUT_DIR / "cenas" / "teste_cena2.mp4"
    final = OUTPUT_DIR / "final" / "teste_composicao.mp4"
    concat_list = OUTPUT_DIR / "cenas" / "concat_list.txt"

    # [1/4] Gerar cena 1
    print("\n[1/4] Gerando vídeo sintético CENA 1...")
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            "color=c=blue:s=1080x1920:d=3:r=30",
            "-vf", "drawtext=text='CENA 1':fontsize=80:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-t", "3", str(cena1)
        ], capture_output=True, text=True, check=True, timeout=30)
        print(f"  ✓ {cena1}")
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Erro: {e.stderr}")
        return 1

    # [2/4] Gerar cena 2
    print("\n[2/4] Gerando vídeo sintético CENA 2...")
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            "color=c=red:s=1080x1920:d=3:r=30",
            "-vf", "drawtext=text='CENA 2':fontsize=80:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-t", "3", str(cena2)
        ], capture_output=True, text=True, check=True, timeout=30)
        print(f"  ✓ {cena2}")
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Erro: {e.stderr}")
        return 1

    # [3/4] Concatenar
    print("\n[3/4] Concatenando cenas...")
    try:
        # Criar lista de concat com paths absolutos
        concat_content = f"file '{cena1.resolve()}'\nfile '{cena2.resolve()}'\n"
        concat_list.write_text(concat_content, encoding="utf-8")

        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(final)
        ], capture_output=True, text=True, check=True, timeout=30)
        print(f"  ✓ Concatenado: {final}")
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Erro na concatenação: {e.stderr}")
        # Tentar re-encode
        print("  Tentando re-encode...")
        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(final)
            ], capture_output=True, text=True, check=True, timeout=60)
            print(f"  ✓ Concatenado (re-encode): {final}")
        except subprocess.CalledProcessError as e2:
            print(f"  ✗ Re-encode falhou: {e2.stderr}")
            return 1

    # [4/4] Verificar com ffprobe
    print("\n[4/4] Verificando resultado com ffprobe...")
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(final)
        ], capture_output=True, text=True, check=True, timeout=10)

        info = json.loads(result.stdout)
        duracao = float(info["format"]["duration"])
        stream = info["streams"][0]
        largura = stream["width"]
        altura = stream["height"]

        print(f"  Duração: {duracao:.1f}s (esperado: ~6s)")
        print(f"  Resolução: {largura}x{altura} (esperado: 1080x1920)")

        if abs(duracao - 6.0) > 1.0:
            print(f"  ✗ Duração fora do esperado!")
            return 1
        if largura != 1080 or altura != 1920:
            print(f"  ✗ Resolução incorreta!")
            return 1

        print(f"  ✓ Tudo OK!")

    except Exception as e:
        print(f"  ✗ Erro no ffprobe: {e}")
        return 1

    print(f"\n{'=' * 50}")
    print("  ✓ TESTE FFMPEG COMPOSIÇÃO: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
