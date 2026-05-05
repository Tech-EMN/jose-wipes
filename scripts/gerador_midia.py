"""Gerador de mídia: vídeo, imagem e áudio para o pipeline José Wipes."""

import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.config import LOGS_DIR, OUTPUT_DIR, gerar_audio as _gerar_audio_config
from scripts.integration_errors import IntegrationFailure, classify_higgsfield_exception

# Flag do Windows para não abrir janela de console
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _subprocess_run(cmd, **kwargs):
    """subprocess.run com CREATE_NO_WINDOW no Windows."""
    if _NO_WINDOW:
        kwargs.setdefault("creationflags", _NO_WINDOW)
    return subprocess.run(cmd, **kwargs)


def log(msg):
    """Log com timestamp no console e arquivo."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{ts}] {msg}"
    print(f"  {linha}")
    log_file = LOGS_DIR / f"geracao_{datetime.now().strftime('%Y%m%d')}.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def gerar_video_higgsfield(modelo, prompt, aspecto="9:16", resolucao="1080p",
                            duracao=6, output_path=None, max_retries=2,
                            reference_image_url=None, extra_arguments=None,
                            raise_on_failure=False):
    """Gera vídeo/imagem via Higgsfield. Retorna path ou None."""
    import higgsfield_client

    if output_path is None:
        is_image = "seedream" in modelo or "text-to-image" in modelo or "soul" in modelo or "reve" in modelo
        ext = ".png" if is_image else ".mp4"
        output_path = OUTPUT_DIR / "cenas" / f"hf_{int(time.time())}{ext}"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    last_failure: IntegrationFailure | None = None

    for tentativa in range(max_retries + 1):
        prompt_atual = prompt
        if tentativa > 0:
            log(f"Retentativa {tentativa}/{max_retries}")
            prompt_atual = "Clean, professional. " + prompt_atual

        log(f"Higgsfield submit: modelo={modelo}, dur={duracao}s")

        try:
            from higgsfield_client import Completed, Failed, NSFW

            is_image_model = "seedream" in modelo or "text-to-image" in modelo or "soul" in modelo or "reve" in modelo
            is_i2v_model = "image-to-video" in modelo or "dop/" in modelo
            is_kling = "kling-video" in modelo

            args = {"prompt": prompt_atual, "aspect_ratio": aspecto}
            if reference_image_url:
                if is_i2v_model:
                    args["image_url"] = reference_image_url
                    log(f"Imagem de input injetada (image-to-video)")
                else:
                    args["reference_image_urls"] = [reference_image_url]
                    log(f"Referência visual do produto injetada")
            if is_image_model:
                # Seedream V4 só aceita 2K ou 4K
                if "seedream" in modelo:
                    args["resolution"] = "4K"
                else:
                    args["resolution"] = resolucao
            else:
                # Kling models só aceitam duração 5 ou 10
                if is_i2v_model or is_kling:
                    duracao = 5 if duracao <= 7 else 10
                args["duration"] = duracao

            if extra_arguments:
                args.update(extra_arguments)

            controller = higgsfield_client.submit(
                application=modelo,
                arguments=args,
            )

            log(f"Request ID: {controller.request_id}")

            for status in controller.poll_request_status(delay=5):
                status_name = type(status).__name__
                log(f"Status: {status_name}")

                if isinstance(status, Completed):
                    break
                elif isinstance(status, NSFW):
                    log("NSFW detectado, retentando com prompt limpo...")
                    last_failure = IntegrationFailure(
                        service="higgsfield",
                        stage="generating",
                        code="generation_failed",
                        user_message="A Higgsfield bloqueou a geração do vídeo por segurança do conteúdo.",
                        technical_message="NSFW detectado durante o polling.",
                        retryable=True,
                        auth_confirmed=True,
                        submit_confirmed=True,
                        render_confirmed=False,
                        reason="nsfw",
                    )
                    break
                elif isinstance(status, Failed):
                    log("Geração falhou")
                    last_failure = IntegrationFailure(
                        service="higgsfield",
                        stage="generating",
                        code="generation_failed",
                        user_message="A Higgsfield não conseguiu concluir a geração do vídeo.",
                        technical_message="Status Failed retornado durante o polling.",
                        retryable=True,
                        auth_confirmed=True,
                        submit_confirmed=True,
                        render_confirmed=False,
                        reason="generation_failed",
                    )
                    break

            if not isinstance(status, Completed):
                continue  # próxima tentativa

            # Buscar resultado
            result = controller.get()

            # Extrair URL do resultado
            url = None
            for getter in [
                lambda r: r.get("video", {}).get("url"),
                lambda r: r.get("image", {}).get("url"),
                lambda r: r.get("output", {}).get("videos", [{}])[0].get("url"),
                lambda r: r.get("output", {}).get("images", [{}])[0].get("url"),
                lambda r: r.get("output", {}).get("url"),
                lambda r: r.get("videos", [{}])[0].get("url"),
                lambda r: r.get("images", [{}])[0].get("url"),
                lambda r: r.get("url"),
                lambda r: r.get("result", {}).get("url"),
            ]:
                try:
                    url = getter(result)
                    if url:
                        break
                except (IndexError, KeyError, TypeError):
                    continue

            if not url:
                log(f"Sem URL no resultado: {result}")
                last_failure = classify_higgsfield_exception(
                    RuntimeError("missing output url"),
                    stage="generating",
                )
                continue

            # Baixar
            result = _subprocess_run(
                ["curl", "-sL", "-o", str(output_path), url],
                capture_output=True, timeout=120
            )
            if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
                last_failure = classify_higgsfield_exception(
                    RuntimeError(f"download failed for output url: {url}"),
                    stage="generating",
                )
                log("✗ Download do output Higgsfield falhou")
                continue
            size = output_path.stat().st_size / (1024 * 1024)
            log(f"✓ Salvo: {output_path} ({size:.1f} MB)")
            return output_path

        except Exception as e:
            last_failure = classify_higgsfield_exception(e, stage="generating")
            log(f"Erro [{last_failure.code}]: {last_failure.technical_message}")

    log(f"✗ Falha após {max_retries + 1} tentativas")
    if raise_on_failure and last_failure is not None:
        raise last_failure
    return None


def gerar_audio_elevenlabs(persona, texto, output_path):
    """Gera áudio via ElevenLabs. Retorna path ou None."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log(f"ElevenLabs: persona={persona}, texto={texto[:50]}...")

    ok = _gerar_audio_config(persona, texto, output_path)
    if ok:
        log(f"✓ Áudio: {output_path}")
        return output_path
    else:
        log(f"✗ Falha ao gerar áudio")
        return None


def combinar_video_audio(video_path, audio_path, output_path):
    """Combina vídeo + áudio com FFmpeg. Retorna path ou None."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log(f"Combinando vídeo + áudio...")

    try:
        _subprocess_run([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "aac",
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest",
            str(output_path)
        ], capture_output=True, text=True, check=True, timeout=120)
        log(f"✓ Combinado: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        log(f"✗ Erro FFmpeg: {e.stderr[:200]}")
        return None


def imagem_para_video_kenburns(imagem_path, duracao_segundos, output_path):
    """Converte imagem estática em vídeo com zoom lento (Ken Burns). Retorna path ou None."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fps = 24
    total_frames = fps * duracao_segundos
    log(f"Ken Burns: {imagem_path} → {duracao_segundos}s")

    # Tentar zoompan
    try:
        _subprocess_run([
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(imagem_path),
            "-vf", f"zoompan=z='min(zoom+0.001,1.10)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={fps}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-t", str(duracao_segundos),
            str(output_path)
        ], capture_output=True, text=True, check=True, timeout=120)
        log(f"✓ Ken Burns: {output_path}")
        return output_path
    except subprocess.CalledProcessError:
        log("Zoompan falhou, tentando estático...")

    # Fallback: imagem estática sem zoom
    try:
        _subprocess_run([
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(imagem_path),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-t", str(duracao_segundos),
            "-r", str(fps),
            str(output_path)
        ], capture_output=True, text=True, check=True, timeout=120)
        log(f"✓ Estático: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        log(f"✗ Erro: {e.stderr[:200]}")
        return None
