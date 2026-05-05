"""Real Higgsfield video smoke test with premium-first fallback and artifact logging."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from scripts.config import HF_API_KEY, HF_API_SECRET, OUTPUT_DIR, obter_url_imagem_produto
from scripts.integration_errors import classify_higgsfield_exception
from scripts.product_reference import prompt_pede_referencia_produto


PRIMARY_MODEL = "google/veo/3.1"
PRIMARY_MODEL_LEGACY = "google/veo/v3.1/text-to-video"
FALLBACK_MODEL = "kling/3.0"
FALLBACK_MODEL_LEGACY = "kling-video/v2.1/master/text-to-video"
THIRD_MODEL = "bytedance/seedance/pro"
THIRD_MODEL_LEGACY = "bytedance/seedance/v1/pro/text-to-video"
SMOKE_TEST_MODELS = (
    PRIMARY_MODEL,
    PRIMARY_MODEL_LEGACY,
    FALLBACK_MODEL,
    FALLBACK_MODEL_LEGACY,
    THIRD_MODEL,
    THIRD_MODEL_LEGACY,
)
SMOKE_TEST_TIMEOUT_SECONDS = 360
SMOKE_TEST_OUTPUT_NAME = "teste_higgsfield_video.mp4"
SMOKE_TEST_LOG_NAME = "higgsfield_video_smoke_test.json"
SMOKE_TEST_PROMPT = (
    "A premium short-form vertical ad for Jose Wipes. In the first second, a confident "
    "Brazilian man turns toward camera in a modern airport bathroom with a subtle pattern "
    "interrupt. Fast cinematic pacing, high contrast lighting, clean masculine styling, "
    "short-form commercial energy. In the final beat, he clearly reveals the official wet "
    "wipes package with confidence. 9:16 portrait format"
)


@dataclass
class SmokeTestAttempt:
    model: str
    request_id: str | None
    status: str
    elapsed_seconds: float
    output_url: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    retryable: bool | None = None
    auth_confirmed: bool | None = None
    submit_confirmed: bool | None = None
    render_confirmed: bool | None = None
    reason: str | None = None


def _status_name(status: object) -> str:
    return type(status).__name__


def _extract_output_url(result: object) -> str | None:
    if not isinstance(result, dict):
        return None

    getters = (
        lambda data: data.get("video", {}).get("url"),
        lambda data: data.get("image", {}).get("url"),
        lambda data: data.get("output", {}).get("videos", [{}])[0].get("url"),
        lambda data: data.get("output", {}).get("images", [{}])[0].get("url"),
        lambda data: data.get("output", {}).get("url"),
        lambda data: data.get("videos", [{}])[0].get("url"),
        lambda data: data.get("images", [{}])[0].get("url"),
        lambda data: data.get("result", {}).get("videos", [{}])[0].get("url"),
        lambda data: data.get("result", {}).get("url"),
        lambda data: data.get("url"),
    )
    for getter in getters:
        try:
            url = getter(result)
        except (AttributeError, IndexError, KeyError, TypeError):
            url = None
        if url:
            return url
    return None


def _download_file(url: str, target: Path) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as response:
        response.raise_for_status()
        with open(target, "wb") as file_handle:
            for chunk in response.iter_bytes():
                file_handle.write(chunk)


def run_higgsfield_video_smoke_test(
    *,
    output_dir: Path | None = None,
    prompt: str = SMOKE_TEST_PROMPT,
    aspect_ratio: str = "9:16",
    duration_seconds: int = 5,
    primary_model: str = PRIMARY_MODEL,
    fallback_model: str = FALLBACK_MODEL,
) -> dict[str, object]:
    """Run a premium-first real Higgsfield video generation smoke test."""

    if not HF_API_KEY or HF_API_KEY.startswith("your_"):
        raise RuntimeError("HF_API_KEY nao configurada.")
    if not HF_API_SECRET or HF_API_SECRET.startswith("your_"):
        raise RuntimeError("HF_API_SECRET nao configurada.")

    import higgsfield_client
    from higgsfield_client import Completed, Failed, NSFW

    output_dir = Path(output_dir or OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = output_dir / SMOKE_TEST_LOG_NAME
    video_path = output_dir / SMOKE_TEST_OUTPUT_NAME

    models = []
    env_primary = os.getenv("HF_MODEL_SEEDANCE_2_0", "").strip()
    env_fallback = os.getenv("HF_MODEL_KLING_3_0", "").strip()
    for candidate in (
        env_primary,
        primary_model,
        PRIMARY_MODEL_LEGACY,
        env_fallback,
        fallback_model,
        FALLBACK_MODEL_LEGACY,
    ):
        if candidate and candidate not in models:
            models.append(candidate)

    attempts: list[SmokeTestAttempt] = []
    reference_image_url = None
    if prompt_pede_referencia_produto(prompt):
        reference_image_url = obter_url_imagem_produto()

    for model in models:
        started_at = time.time()
        request_id = None

        try:
            arguments: dict[str, object] = {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "duration": duration_seconds,
            }
            if reference_image_url:
                arguments["reference_image_urls"] = [reference_image_url]

            controller = higgsfield_client.submit(
                application=model,
                arguments=arguments,
            )
            request_id = getattr(controller, "request_id", None)

            final_status = None
            for status in controller.poll_request_status(delay=5):
                final_status = status
                if time.time() - started_at > SMOKE_TEST_TIMEOUT_SECONDS:
                    raise TimeoutError(
                        f"Polling excedeu {SMOKE_TEST_TIMEOUT_SECONDS}s para o modelo {model}."
                    )
                if isinstance(status, (Completed, Failed, NSFW)):
                    break

            status_label = _status_name(final_status)
            elapsed = round(time.time() - started_at, 1)

            if final_status is None:
                raise RuntimeError("A Higgsfield nao retornou nenhum status final.")

            if isinstance(final_status, Failed):
                error_message = getattr(final_status, "message", None) or repr(final_status)
                attempts.append(
                    SmokeTestAttempt(
                        model=model,
                        request_id=request_id,
                        status=status_label,
                        elapsed_seconds=elapsed,
                        error_type="generation_failed",
                        error_message=error_message,
                        auth_confirmed=True,
                        submit_confirmed=True,
                        render_confirmed=False,
                        reason="generation_failed",
                    )
                )
                continue

            if isinstance(final_status, NSFW):
                attempts.append(
                    SmokeTestAttempt(
                        model=model,
                        request_id=request_id,
                        status=status_label,
                        elapsed_seconds=elapsed,
                        error_type="nsfw",
                        error_message="Conteudo bloqueado como NSFW.",
                        auth_confirmed=True,
                        submit_confirmed=True,
                        render_confirmed=False,
                        reason="nsfw",
                    )
                )
                continue

            result = controller.get()
            output_url = _extract_output_url(result)
            if not output_url:
                attempts.append(
                    SmokeTestAttempt(
                        model=model,
                        request_id=request_id,
                        status=status_label,
                        elapsed_seconds=elapsed,
                        error_type="missing_output_url",
                        error_message="A resposta concluida nao trouxe URL de output.",
                        retryable=True,
                        auth_confirmed=True,
                        submit_confirmed=True,
                        render_confirmed=False,
                        reason="missing_output_url",
                    )
                )
                continue

            _download_file(output_url, video_path)
            size_mb = round(video_path.stat().st_size / (1024 * 1024), 2)

            attempts.append(
                SmokeTestAttempt(
                    model=model,
                    request_id=request_id,
                    status=status_label,
                    elapsed_seconds=elapsed,
                    output_url=output_url,
                )
            )

            payload = {
                "success": True,
                "primary_model": primary_model,
                "fallback_model": fallback_model,
                "candidate_models": models,
                "selected_model": model,
                "request_id": request_id,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "duration_seconds": duration_seconds,
                "reference_image_used": bool(reference_image_url),
                "video_path": str(video_path),
                "video_size_mb": size_mb,
                "attempts": [asdict(item) for item in attempts],
            }
            log_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return payload

        except Exception as exc:
            failure = classify_higgsfield_exception(exc, stage="generating")
            attempts.append(
                SmokeTestAttempt(
                    model=model,
                    request_id=request_id,
                    status="exception",
                    elapsed_seconds=round(time.time() - started_at, 1),
                    error_type=failure.code,
                    error_message=failure.technical_message,
                    retryable=failure.retryable,
                    auth_confirmed=failure.auth_confirmed,
                    submit_confirmed=failure.submit_confirmed,
                    render_confirmed=failure.render_confirmed,
                    reason=failure.reason,
                )
            )

    failure_payload = {
        "success": False,
        "primary_model": primary_model,
        "fallback_model": fallback_model,
        "candidate_models": models,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "duration_seconds": duration_seconds,
        "reference_image_used": bool(reference_image_url),
        "video_path": str(video_path),
        "attempts": [asdict(item) for item in attempts],
    }
    log_path.write_text(
        json.dumps(failure_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    raise RuntimeError(
        f"Smoke test Higgsfield falhou. Consulte {log_path} para diagnostico detalhado."
    )


def main() -> int:
    print("=" * 50)
    print("TESTE: Higgsfield Video Smoke Test")
    print("=" * 50)

    try:
        payload = run_higgsfield_video_smoke_test()
    except Exception as exc:
        print(f"  x {exc}")
        return 1

    print(f"  + Modelo usado: {payload['selected_model']}")
    print(f"  + Video salvo em: {payload['video_path']}")
    print("  + Smoke test Higgsfield video: PASSOU")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
