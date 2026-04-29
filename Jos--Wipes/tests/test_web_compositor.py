"""Valida composição final em 9:16 e 16:9 para o web studio."""

import sys
import json
import shutil
import subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.compositor import compor_video_final


def gerar_video_teste(output_path: Path, width: int, height: int, color: str) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={width}x{height}:d=2:r=24",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )


def probe_dimensions(video_path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    info = json.loads(result.stdout)
    stream = info["streams"][0]
    return stream["width"], stream["height"]


def main():
    print("=" * 50)
    print("TESTE: Web Compositor")
    print("=" * 50)

    temp_path = Path(__file__).parent.parent / "output" / "test_web_compositor"
    if temp_path.exists():
        shutil.rmtree(temp_path, ignore_errors=True)
    temp_path.mkdir(parents=True, exist_ok=True)

    try:
        vertical_1 = temp_path / "vertical_1.mp4"
        vertical_2 = temp_path / "vertical_2.mp4"
        horizontal_1 = temp_path / "horizontal_1.mp4"
        horizontal_2 = temp_path / "horizontal_2.mp4"

        gerar_video_teste(vertical_1, 1080, 1920, "blue")
        gerar_video_teste(vertical_2, 1080, 1920, "red")
        gerar_video_teste(horizontal_1, 1920, 1080, "green")
        gerar_video_teste(horizontal_2, 1920, 1080, "yellow")

        vertical_final = compor_video_final(
            [str(vertical_1), str(vertical_2)],
            "vertical_test",
            largura=1080,
            altura=1920,
            output_dir=temp_path / "vertical_final",
        )
        horizontal_final = compor_video_final(
            [str(horizontal_1), str(horizontal_2)],
            "horizontal_test",
            largura=1920,
            altura=1080,
            output_dir=temp_path / "horizontal_final",
        )

        if not vertical_final or not horizontal_final:
            print("  ✗ A composição final retornou None")
            return 1

        if probe_dimensions(vertical_final) != (1080, 1920):
            print(f"  ✗ Dimensão vertical incorreta: {probe_dimensions(vertical_final)}")
            return 1

        if probe_dimensions(horizontal_final) != (1920, 1080):
            print(f"  ✗ Dimensão horizontal incorreta: {probe_dimensions(horizontal_final)}")
            return 1

        print("  ✓ Composição funciona em vertical e horizontal")
        print("-" * 50)
        print("  ✓ TESTE WEB COMPOSITOR: PASSOU")
        return 0
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
