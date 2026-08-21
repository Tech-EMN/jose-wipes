"""Compositor de vídeo: normalização, concatenação, overlays para José Wipes."""

import os
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.config import OUTPUT_DIR, ASSETS_DIR, obter_path_imagem_produto

# Flag do Windows para não abrir janela de console
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


_DEFAULT_FFMPEG_TIMEOUT = int(os.getenv("JW_FFMPEG_TIMEOUT", "300"))


def _subprocess_run(cmd, **kwargs):
    """subprocess.run com CREATE_NO_WINDOW no Windows e timeout padrao.

    Todas as chamadas FFmpeg recebem timeout=300s por padrao,
    evitando que o worker bloqueie indefinidamente em video corrompido.
    Configure JW_FFMPEG_TIMEOUT no .env para ajustar.
    """
    kwargs.setdefault("timeout", _DEFAULT_FFMPEG_TIMEOUT)
    if _NO_WINDOW:
        kwargs.setdefault("creationflags", _NO_WINDOW)
    return subprocess.run(cmd, **kwargs)


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


def _obter_dimensoes_video(video_path):
    try:
        probe = _subprocess_run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        stream = json.loads(probe.stdout)["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except (subprocess.SubprocessError, OSError, ValueError, TypeError, KeyError, IndexError):
        return None


def _detectar_crop_sem_letterbox(input_path, sample_seconds=4):
    """Detecta barras pretas (letterbox/pillarbox) e retorna 'W:H:X:Y' ou None.

    Alguns modelos (Kling, Veo) renderizam 9:16 com letterbox embutido quando
    interpretam mal o aspect_ratio. Roda cropdetect amostrando o miolo do vídeo
    pra remover essas barras antes de escalar.
    """
    try:
        proc = _subprocess_run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-ss", "0.5",
                "-i", str(input_path),
                "-t", str(sample_seconds),
                "-vf", "cropdetect=24:2:0",
                "-f", "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.SubprocessError:
        return None

    crop_value = None
    for line in (proc.stderr or "").splitlines():
        idx = line.find("crop=")
        if idx == -1:
            continue
        candidate = line[idx + len("crop="):].split()[0].strip()
        if candidate.count(":") == 3:
            crop_value = candidate
    return crop_value


def normalizar_cena(input_path, output_path, largura=1080, altura=1920, fps=24):
    """Normaliza vídeo: resolução, fps, codec. Retorna path ou None."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Verificar se tem áudio
    probe = _subprocess_run(
        ["ffprobe", "-v", "quiet", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "json", str(input_path)],
        capture_output=True, text=True, timeout=10
    )
    has_audio = '"codec_type"' in probe.stdout

    dimensions = _obter_dimensoes_video(input_path)
    pre_crop = (
        None
        if dimensions == (largura, altura)
        else _detectar_crop_sem_letterbox(input_path)
    )
    pre_filter = f"crop={pre_crop}," if pre_crop else ""
    if pre_crop:
        log(f"Letterbox detectado, removendo barras: {pre_crop}")

    vf = (
        f"{pre_filter}scale={largura}:{altura}:force_original_aspect_ratio=increase,"
        f"crop={largura}:{altura},setsar=1,fps={fps}"
    )

    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-vf", vf,
           "-c:v", "libx264", "-pix_fmt", "yuv420p"]

    if has_audio:
        cmd.extend(["-c:a", "aac", "-ar", "44100"])
    else:
        # Gerar silêncio
        cmd.extend(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                     "-c:a", "aac", "-shortest"])
        # Rebuild cmd with two inputs
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100",
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest",
        ]

    cmd.append(str(output_path))

    try:
        _subprocess_run(cmd, capture_output=True, text=True, check=True, timeout=120)
        log(f"✓ Normalizado: {output_path.name}")
        return output_path
    except subprocess.CalledProcessError as e:
        log(f"✗ Normalização falhou: {e.stderr[:200]}")
        return None


def concatenar_cenas(cenas_paths, output_path):
    """Concatena lista de vídeos. Retorna path ou None."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    concat_file = output_path.parent / "concat_list.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for p in cenas_paths:
            f.write(f"file '{Path(p).resolve()}'\n")

    # Tentar stream copy
    try:
        _subprocess_run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-c", "copy", str(output_path)
        ], capture_output=True, text=True, check=True, timeout=120)
        log(f"✓ Concatenado (copy): {output_path.name}")
        concat_file.unlink(missing_ok=True)
        return output_path
    except subprocess.CalledProcessError:
        pass

    # Fallback: re-encode
    try:
        _subprocess_run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(output_path)
        ], capture_output=True, text=True, check=True, timeout=300)
        log(f"✓ Concatenado (re-encode): {output_path.name}")
        concat_file.unlink(missing_ok=True)
        return output_path
    except subprocess.CalledProcessError as e:
        log(f"✗ Concatenação falhou: {e.stderr[:200]}")
        concat_file.unlink(missing_ok=True)
        return None


def adicionar_logo_overlay(video_path, logo_path, output_path, posicao="inferior_direito",
                            tamanho_pct=12, opacidade=0.9):
    """Adiciona logo overlay ao vídeo. Retorna path ou None."""
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if logo_path is None:
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path
    logo_path = Path(logo_path)

    if not logo_path.exists():
        log(f"Logo não encontrado ({logo_path}), copiando sem overlay")
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path

    # Posição do overlay
    pos_map = {
        "inferior_direito": "W-w-20:H-h-20",
        "inferior_esquerdo": "20:H-h-20",
        "superior_direito": "W-w-20:20",
        "centro": "(W-w)/2:(H-h)/2",
    }
    pos = pos_map.get(posicao, pos_map["inferior_direito"])

    filter_complex = (
        f"[1:v]scale=iw*{tamanho_pct}/100:-1,format=rgba,"
        f"colorchannelmixer=aa={opacidade}[logo];"
        f"[0:v][logo]overlay={pos}[out]"
    )

    try:
        _subprocess_run([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(logo_path),
            "-filter_complex", filter_complex,
            "-map", "[out]", "-map", "0:a?",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(output_path)
        ], capture_output=True, text=True, check=True, timeout=120)
        log(f"✓ Logo overlay: {output_path.name}")
        return output_path
    except subprocess.CalledProcessError as e:
        log(f"✗ Logo overlay falhou: {e.stderr[:200]}")
        # Fallback: copiar sem logo
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path


def adicionar_texto_overlay(video_path, texto, output_path, posicao="centro_inferior"):
    """Adiciona texto overlay ao vídeo. Retorna path ou None."""
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Escapar caracteres especiais para FFmpeg drawtext
    texto_escaped = texto.replace("'", "\\'").replace(":", "\\:").replace("\\", "\\\\")

    pos_map = {
        "centro_inferior": "x=(w-text_w)/2:y=h-text_h-80",
        "centro": "x=(w-text_w)/2:y=(h-text_h)/2",
        "topo": "x=(w-text_w)/2:y=80",
    }
    xy = pos_map.get(posicao, pos_map["centro_inferior"])

    try:
        _subprocess_run([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"drawtext=text='{texto_escaped}':fontsize=42:fontcolor=white:borderw=3:bordercolor=black:{xy}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(output_path)
        ], capture_output=True, text=True, check=True, timeout=120)
        log(f"✓ Texto overlay: {output_path.name}")
        return output_path
    except subprocess.CalledProcessError as e:
        log(f"✗ Texto overlay falhou: {e.stderr[:200]}")
        return None


def compor_produto_na_imagem(imagem_path, output_path, produto_path=None,
                              posicao="mao_direita", tamanho_pct=30):
    """Compõe a imagem real do produto sobre uma imagem de cena (ex: na mão do personagem).
    Retorna path da imagem composta ou None.
    posicao: mao_direita, mao_esquerda, centro, centro_inferior
    """
    imagem_path = Path(imagem_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if produto_path is None:
        produto_path = obter_path_imagem_produto()
    produto_path = Path(produto_path)

    if not produto_path.exists():
        log(f"Imagem do produto não encontrada ({produto_path})")
        return None

    # Posições otimizadas para parecer que está na mão do personagem
    # Mãos ficam tipicamente no terço central vertical (~35-50% da altura)
    pos_map = {
        "mao_direita": "(W-w)/2+W*0.05:H*0.32",
        "mao_esquerda": "(W-w)/2-W*0.05:H*0.32",
        "mao_centro": "(W-w)/2:H*0.30",
        "centro": "(W-w)/2:(H-h)/2",
        "centro_inferior": "(W-w)/2:H*0.55",
    }
    pos = pos_map.get(posicao, pos_map["mao_direita"])

    try:
        _subprocess_run([
            "ffmpeg", "-y",
            "-i", str(imagem_path),
            "-i", str(produto_path),
            "-filter_complex",
            f"[1:v]scale=iw*{tamanho_pct}/100:-1[prod];[0:v][prod]overlay={pos}:format=auto[out]",
            "-map", "[out]",
            str(output_path)
        ], capture_output=True, text=True, check=True, timeout=60)
        log(f"✓ Produto composto na imagem: {output_path.name}")
        return output_path
    except subprocess.CalledProcessError as e:
        log(f"✗ Composição produto falhou: {e.stderr[:200]}")
        return None


def overlay_produto(video_path, output_path, produto_path=None,
                     posicao="centro", tamanho_pct=55, inicio_seg=None,
                     fade_in=0.5):
    """Sobrepõe a imagem real do produto sobre o vídeo.
    posicao: centro, centro_inferior, direita, esquerda
    inicio_seg: momento em que aparece (None = todo o vídeo)
    """
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if produto_path is None:
        produto_path = obter_path_imagem_produto()
    produto_path = Path(produto_path)

    if not produto_path.exists():
        log(f"Imagem do produto não encontrada ({produto_path})")
        return None

    # Posições
    pos_map = {
        "centro": ("(W-w)/2", "(H-h)/2"),
        "centro_inferior": ("(W-w)/2", "H-h-150"),
        "direita": ("W-w-60", "(H-h)/2"),
        "esquerda": ("60", "(H-h)/2"),
    }
    x_pos, y_pos = pos_map.get(posicao, pos_map["centro"])

    # Escalar produto para % da largura do vídeo, com fade in suave a partir de inicio_seg
    dimensions = _obter_dimensoes_video(video_path)
    if dimensions is None:
        log(f"Não foi possível obter as dimensões do vídeo ({video_path})")
        return None
    product_width = max(1, round(dimensions[0] * float(tamanho_pct) / 100))
    fade_dur = max(0.0, float(fade_in or 0.0))
    still_image_filter = "[1:v]loop=loop=-1:size=1:start=0,setpts=N/(24*TB),"
    if inicio_seg is not None and float(inicio_seg) > 0:
        start = float(inicio_seg)
        if fade_dur > 0:
            scale_filter = (
                f"{still_image_filter}scale={product_width}:-1,format=rgba,"
                f"fade=t=in:st={start}:d={fade_dur}:alpha=1,"
                "split=2[prod][shadow_src]"
            )
        else:
            scale_filter = (
                f"{still_image_filter}scale={product_width}:-1,format=rgba,"
                "split=2[prod][shadow_src]"
            )
        enable_filter = f":enable='gte(t,{start})'"
    else:
        scale_filter = (
            f"{still_image_filter}scale={product_width}:-1,format=rgba,"
            "split=2[prod][shadow_src]"
        )
        enable_filter = ""

    shadow_filter = (
        "[shadow_src]colorchannelmixer=rr=0:gg=0:bb=0:aa=0.3,"
        "gblur=sigma=12[shadow]"
    )
    shadow_overlay = (
        f"[0:v][shadow]overlay=({x_pos})+8:({y_pos})+18"
        f"{enable_filter}:format=auto:shortest=1[with_shadow]"
    )
    product_overlay = (
        f"[with_shadow][prod]overlay={x_pos}:{y_pos}"
        f"{enable_filter}:format=auto:shortest=1[out]"
    )
    filter_complex = ";".join(
        (scale_filter, shadow_filter, shadow_overlay, product_overlay)
    )

    try:
        _subprocess_run([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(produto_path),
            "-filter_complex", filter_complex,
            "-map", "[out]", "-map", "0:a?",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(output_path)
        ], capture_output=True, text=True, check=True, timeout=120)
        log(f"✓ Produto overlay: {output_path.name}")
        return output_path
    except subprocess.CalledProcessError as e:
        log(f"✗ Produto overlay falhou: {e.stderr[:200]}")
        return None


def gerar_card_final_com_produto(output_path, produto_path=None, duracao=4,
                                   largura=1080, altura=1920):
    """Gera card final usando a imagem REAL do produto sobre fundo preto."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if produto_path is None:
        produto_path = obter_path_imagem_produto()
    produto_path = Path(produto_path)

    if not produto_path.exists():
        log(f"Imagem do produto não encontrada ({produto_path})")
        return None

    fps = 24
    # Fundo preto + produto BEM grande centralizado com zoom lento
    filter_complex = (
        f"color=black:s={largura}x{altura}:d={duracao}:r={fps}[bg];"
        f"[1:v]scale={int(largura*0.92)}:-1[prod];"
        f"[bg][prod]overlay=(W-w)/2:(H-h)/2-60:format=auto,"
        f"zoompan=z='min(zoom+0.0008,1.05)':d={fps*duracao}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={largura}x{altura}:fps={fps}[out]"
    )

    try:
        _subprocess_run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=black:s={largura}x{altura}:d={duracao}:r={fps}",
            "-i", str(produto_path),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-t", str(duracao),
            str(output_path)
        ], capture_output=True, text=True, check=True, timeout=120)
        log(f"✓ Card final com produto real: {output_path.name}")
        return output_path
    except subprocess.CalledProcessError as e:
        log(f"✗ Card final com produto falhou: {e.stderr[:300]}")
        # Fallback simples: produto estático sobre fundo preto
        try:
            _subprocess_run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=black:s={largura}x{altura}:d={duracao}:r={fps}",
                "-i", str(produto_path),
                "-filter_complex",
                f"[1:v]scale={int(largura*0.92)}:-1[prod];[0:v][prod]overlay=(W-w)/2:(H-h)/2-60[out]",
                "-map", "[out]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-t", str(duracao),
                str(output_path)
            ], capture_output=True, text=True, check=True, timeout=120)
            log(f"✓ Card final (fallback estático): {output_path.name}")
            return output_path
        except subprocess.CalledProcessError as e2:
            log(f"✗ Card final fallback falhou: {e2.stderr[:200]}")
            return None


def gerar_card_logo(output_path, logo_path, duracao=3, largura=1080, altura=1920, fundo="white"):
    """Gera card final limpo com a logo/embalagem real da marca sobre fundo neutro."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logo_path = Path(logo_path)

    if not logo_path.exists():
        log(f"Imagem não encontrada para card final ({logo_path})")
        return None

    fps = 24
    logo_width = int(largura * 0.80)

    try:
        _subprocess_run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color={fundo}:s={largura}x{altura}:d={duracao}:r={fps}",
            "-i", str(logo_path),
            "-filter_complex",
            f"[1:v]scale={logo_width}:-1,format=rgba[logo];[0:v][logo]overlay=(W-w)/2:(H-h)/2:format=auto[out]",
            "-map", "[out]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-t", str(duracao),
            str(output_path)
        ], capture_output=True, text=True, check=True, timeout=60)
        log(f"✓ Card logo: {output_path.name}")
        return output_path
    except subprocess.CalledProcessError as e:
        log(f"✗ Card logo falhou: {e.stderr[:200]}")
        return None


def _limitar_duracao(video_path, duracao_segundos):
    video_path = Path(video_path)
    trimmed_path = video_path.with_name(f"_{video_path.stem}_trimmed{video_path.suffix}")
    target_duration = f"{float(duracao_segundos):.3f}"

    try:
        _subprocess_run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-vf",
                (
                    f"tpad=stop_mode=clone:stop_duration={target_duration},"
                    f"trim=duration={target_duration},setpts=PTS-STARTPTS"
                ),
                "-af",
                (
                    f"apad=pad_dur={target_duration},"
                    f"atrim=duration={target_duration},asetpts=PTS-STARTPTS"
                ),
                "-t",
                target_duration,
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "44100",
                "-movflags",
                "+faststart",
                str(trimmed_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
        trimmed_path.replace(video_path)
        log(f"✓ Duração ajustada para {target_duration}s")
        return video_path
    except (subprocess.CalledProcessError, OSError) as exc:
        trimmed_path.unlink(missing_ok=True)
        log(f"✗ Ajuste de duração falhou: {exc}")
        return None


def compor_video_final(cenas_geradas, titulo, logo_path=None, *,
                       largura=1080, altura=1920, fps=24, output_dir=None,
                       duracao_maxima=None):
    """Pipeline completo: normalizar → concatenar → logo → exportar. Retorna path ou None."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    titulo_safe = "".join(c if c.isalnum() or c in "_ -" else "_" for c in titulo)
    final_dir = Path(output_dir) if output_dir else OUTPUT_DIR / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    log(f"Compondo vídeo final: '{titulo}' ({len(cenas_geradas)} cenas)")

    # 1. Normalizar
    normalizados = []
    temp_files = []
    for i, cena in enumerate(cenas_geradas):
        cena_path = Path(cena)
        norm_path = final_dir / f"_norm_{i:02d}_{cena_path.stem}.mp4"
        result = normalizar_cena(
            cena_path, norm_path, largura=largura, altura=altura, fps=fps
        )
        if result:
            normalizados.append(result)
            temp_files.append(norm_path)
        else:
            log(f"Cena {i+1} falhou na normalização, pulando")

    if not normalizados:
        log("✗ Nenhuma cena normalizada com sucesso!")
        return None

    # 2. Concatenar
    concat_path = final_dir / f"_concat_{ts}.mp4"
    temp_files.append(concat_path)
    result = concatenar_cenas(normalizados, concat_path)
    if not result:
        _cleanup(temp_files)
        return None

    # 3. Logo overlay
    final_path = final_dir / f"{titulo_safe}_{ts}.mp4"
    result = adicionar_logo_overlay(concat_path, logo_path, final_path)
    if not result:
        final_path = concat_path  # usar sem logo

    if duracao_maxima is not None:
        result = _limitar_duracao(final_path, duracao_maxima)
        if not result:
            _cleanup(temp_files)
            return None
        final_path = result

    # 4. Info do resultado
    try:
        probe = _subprocess_run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(final_path)],
            capture_output=True, text=True, timeout=10
        )
        info = json.loads(probe.stdout)
        duracao = float(info.get("format", {}).get("duration", 0))
        tamanho = int(info.get("format", {}).get("size", 0)) / (1024 * 1024)
        log(f"✓ VÍDEO FINAL: {final_path}")
        log(f"  Duração: {duracao:.1f}s | Tamanho: {tamanho:.1f} MB")
    except Exception:
        log(f"✓ VÍDEO FINAL: {final_path}")

    # 5. Limpar temporários
    _cleanup(temp_files)

    return final_path


def _cleanup(temp_files):
    for f in temp_files:
        try:
            Path(f).unlink(missing_ok=True)
        except Exception:
            pass
