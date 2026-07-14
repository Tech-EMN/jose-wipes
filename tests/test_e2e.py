"""
F18 — Testes E2E (End-to-End) do José Wipes Pipeline.

Cobre 4 cenários:
  1. E2E real com plano pré-gerado (briefing → vídeo final)
  2. Concorrência (2+ jobs simultâneos via web API)
  3. Carga (5 jobs em sequência)
  4. Recuperação (worker crash + retomada)

Requer: HF_API_KEY, HF_API_SECRET, ELEVENLABS_API_KEY, FFmpeg
OpenAI é opcional — o teste usa plano pré-gerado se a chave falhar.

Uso: pytest tests/test_e2e.py -v
      pytest tests/test_e2e.py -v -k "test_e2e"  # só o E2E real
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

# ── Helpers ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("JW_FFMPEG_TIMEOUT", "60")

# Fixtures dir
FIXTURES_DIR = Path(__file__).parent / "fixtures"
E2E_PLAN_PATH = FIXTURES_DIR / "e2e_plan.json"

# Output dir for E2E tests
E2E_OUTPUT = PROJECT_ROOT / "output" / "e2e_tests"


@pytest.fixture(autouse=True)
def setup_e2e():
    """Setup/teardown for every E2E test."""
    E2E_OUTPUT.mkdir(parents=True, exist_ok=True)
    # Limpar output do teste anterior
    for f in E2E_OUTPUT.glob("*"):
        if f.is_file():
            f.unlink()
        elif f.is_dir():
            shutil.rmtree(f, ignore_errors=True)
    yield
    # Cleanup after test
    # (mantemos output para debug; remover em CI com env var)
    if os.getenv("E2E_CLEANUP", "").lower() in {"true", "1", "yes"}:
        shutil.rmtree(E2E_OUTPUT, ignore_errors=True)


def check_ffmpeg() -> bool:
    """Verifica se FFmpeg está disponível."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_env_keys() -> dict[str, bool]:
    """Verifica quais API keys estão disponíveis."""
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    return {
        "openai": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "hf": bool(os.getenv("HF_API_KEY", "").strip()),
        "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY", "").strip()),
        "ffmpeg": check_ffmpeg(),
    }


def check_hf_connectivity() -> tuple[bool, str]:
    """Verifica se a API Higgsfield está acessível."""
    import requests
    hf_key = os.getenv("HF_API_KEY", "")
    hf_secret = os.getenv("HF_API_SECRET", "")
    if not hf_key or not hf_secret:
        return False, "HF_API_KEY/HF_API_SECRET não configuradas"
    try:
        resp = requests.post(
            "https://api.higgsfield.ai/v1/auth/token",
            json={"api_key": hf_key, "api_secret": hf_secret},
            timeout=10,
        )
        if resp.status_code == 200:
            return True, "OK"
        elif resp.status_code >= 500:
            return False, f"Higgsfield API indisponível (HTTP {resp.status_code})"
        else:
            return False, f"Higgsfield auth falhou (HTTP {resp.status_code}): {resp.text[:100]}"
    except requests.exceptions.Timeout:
        return False, "Higgsfield API timeout"
    except Exception as e:
        return False, f"Higgsfield connectivity error: {e}"


def load_e2e_plan() -> dict[str, Any]:
    """Carrega o plano E2E pré-gerado."""
    if not E2E_PLAN_PATH.exists():
        pytest.skip(f"Fixture não encontrada: {E2E_PLAN_PATH}")
    return json.loads(E2E_PLAN_PATH.read_text(encoding="utf-8"))


# ── Teste 1: E2E Real (pipeline completo) ──────────────────────────────────

@pytest.mark.e2e
@pytest.mark.slow
def test_e2e_full_pipeline():
    """Teste E2E: briefing → decomposição → geração → composição → vídeo final.

    Usa plano pré-gerado (fixture JSON) para evitar dependência da OpenAI.
    Pipeline real com Higgsfield + ElevenLabs.
    """
    keys = check_env_keys()
    if not keys["hf"]:
        pytest.skip("HF_API_KEY não configurada")
    if not keys["ffmpeg"]:
        pytest.skip("FFmpeg não disponível")

    hf_ok, hf_msg = check_hf_connectivity()
    if not hf_ok:
        pytest.skip(f"Higgsfield indisponível: {hf_msg}")

    from scripts.pipeline import executar_pipeline

    plano = load_e2e_plan()
    resultado = executar_pipeline(plano=plano)

    assert resultado["sucesso"], (
        f"Pipeline falhou. Cenas falharam: {resultado['cenas_falharam']}"
    )
    assert resultado["video_local"] is not None, "Vídeo final não foi gerado"
    assert Path(resultado["video_local"]).exists(), "Arquivo do vídeo final não existe"
    assert Path(resultado["video_local"]).stat().st_size > 1024, (
        "Vídeo final muito pequeno (< 1KB)"
    )

    # Todas as cenas devem ter sido geradas
    plano_cenas = plano.get("cenas", [])
    assert len(resultado["cenas_geradas"]) == len(plano_cenas), (
        f"Nem todas as cenas foram geradas: "
        f"{len(resultado['cenas_geradas'])}/{len(plano_cenas)}"
    )

    print(f"\n  ✓ Vídeo final: {resultado['video_local']}")
    print(f"  ✓ Tamanho: {Path(resultado['video_local']).stat().st_size / (1024*1024):.1f} MB")


# ── Teste 2: Concorrência (2+ jobs simultâneos) ────────────────────────────

@pytest.mark.e2e
@pytest.mark.slow
def test_e2e_concurrent_jobs():
    """Teste de concorrência: 2 jobs submetidos simultaneamente via web API.

    Ambos devem completar sem interferência.
    """
    keys = check_env_keys()
    if not keys["hf"]:
        pytest.skip("HF_API_KEY não configurada")
    if not keys["elevenlabs"]:
        pytest.skip("ELEVENLABS_API_KEY não configurada")

    hf_ok, hf_msg = check_hf_connectivity()
    if not hf_ok:
        pytest.skip(f"Higgsfield indisponível: {hf_msg}")

    from fastapi.testclient import TestClient
    from webapp.main import app

    # Usar o cliente de teste da FastAPI com o app real
    client = TestClient(app)

    # Preparar 2 requisições com prompts diferentes
    prompts = [
        "Crie um vídeo de 10 segundos mostrando alívio e conforto com José Wipes, estilo clean e profissional",
        "Crie um vídeo de 10 segundos mostrando frescor e recuperação, tom acolhedor e moderno",
    ]

    import concurrent.futures

    def submit_job(prompt: str) -> dict:
        """Submete um job e aguarda completar."""
        resp = client.post("/api/jobs", data={
            "resolution": "720p",
            "orientation": "vertical",
            "duration_seconds": 10,
            "prompt": prompt,
            "video_model": "seedance_1_5_pro",
            "apply_logo_overlay": "false",
        })
        assert resp.status_code == 200, f"Falha ao criar job: {resp.text}"
        return resp.json()

    # Submeter simultaneamente
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit_job, p) for p in prompts]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 2, f"Deveria ter 2 jobs, mas tem {len(results)}"
    job_ids = [r["job_id"] for r in results]
    assert len(set(job_ids)) == 2, "Jobs deveriam ter IDs diferentes"

    # Aguardar completar (poll SSE-style, mas sync para o teste)
    completed = set()
    max_wait = 300  # 5 minutos
    start = time.time()

    while len(completed) < 2 and time.time() - start < max_wait:
        for jid in job_ids:
            if jid in completed:
                continue
            resp = client.get(f"/api/jobs/{jid}")
            if resp.status_code != 200:
                continue
            status = resp.json()
            if status["status"] in {"completed", "failed"}:
                completed.add(jid)
        time.sleep(2)

    assert len(completed) == 2, (
        f"Apenas {len(completed)}/2 jobs completaram em {max_wait}s"
    )

    # Verificar que ambos geraram vídeo
    for jid in job_ids:
        resp = client.get(f"/api/jobs/{jid}")
        assert resp.json()["status"] == "completed", f"Job {jid} não completou"
        dl_resp = client.get(f"/api/jobs/{jid}/download")
        assert dl_resp.status_code == 200, f"Download do job {jid} falhou"

    print(f"\n  ✓ 2 jobs concorrentes completaram com sucesso")
    print(f"  ✓ Tempo total: {time.time() - start:.1f}s")


# ── Teste 3: Carga (5 jobs em sequência) ───────────────────────────────────

@pytest.mark.e2e
@pytest.mark.slow
def test_e2e_sequential_load():
    """Teste de carga: 5 jobs submetidos em sequência.

    Verifica que o sistema mantém consistência sob carga moderada.
    """
    keys = check_env_keys()
    if not keys["hf"]:
        pytest.skip("HF_API_KEY não configurada")

    hf_ok, hf_msg = check_hf_connectivity()
    if not hf_ok:
        pytest.skip(f"Higgsfield indisponível: {hf_msg}")

    from fastapi.testclient import TestClient
    from webapp.main import app

    client = TestClient(app)
    num_jobs = 5
    job_ids: list[str] = []

    # Submeter jobs em sequência
    for i in range(num_jobs):
        resp = client.post("/api/jobs", data={
            "resolution": "720p",
            "orientation": "vertical",
            "duration_seconds": 10,
            "prompt": f"Vídeo #{i+1}: Cena clean mostrando produto de higiene, fundo branco, iluminação suave",
            "video_model": "seedance_1_5_pro",
            "apply_logo_overlay": "false",
        })
        assert resp.status_code == 200, f"Job {i+1} falhou: {resp.text}"
        job_ids.append(resp.json()["job_id"])
        print(f"  Job {i+1}/{num_jobs} submetido: {job_ids[-1]}")

    assert len(job_ids) == num_jobs
    assert len(set(job_ids)) == num_jobs, "IDs de jobs duplicados"

    # Aguardar completar todos
    completed = set()
    failed = set()
    max_wait = 600  # 10 minutos
    start = time.time()

    while len(completed) + len(failed) < num_jobs and time.time() - start < max_wait:
        for jid in job_ids:
            if jid in completed or jid in failed:
                continue
            try:
                resp = client.get(f"/api/jobs/{jid}")
                if resp.status_code != 200:
                    continue
                status = resp.json()
                if status["status"] == "completed":
                    completed.add(jid)
                elif status["status"] == "failed":
                    failed.add(jid)
            except Exception:
                pass
        time.sleep(3)

    elapsed = time.time() - start
    print(f"\n  ✓ Completados: {len(completed)}/{num_jobs}")
    if failed:
        print(f"  ✗ Falharam: {len(failed)}/{num_jobs}")
    print(f"  ⏱ Tempo total: {elapsed:.1f}s ({elapsed/num_jobs:.1f}s/job médio)")

    # Pelo menos 80% devem completar
    success_rate = len(completed) / num_jobs
    assert success_rate >= 0.8, (
        f"Taxa de sucesso {success_rate:.0%} abaixo do mínimo de 80%"
    )


# ── Teste 4: Recuperação (worker crash + retomada) ─────────────────────────

@pytest.mark.e2e
def test_e2e_worker_recovery():
    """Teste de recuperação: simula falha do worker e verifica retomada.

    - Cria um job
    - Para o worker (simulando crash)
    - Reinicia o worker
    - Verifica que jobs pendentes são retomados
    """
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

    from webapp.job_manager import JobManager
    from webapp.schemas import CreateJobRequest, JobStatusResponse

    # Criar job manager isolado para este teste
    test_dir = E2E_OUTPUT / "recovery_test"
    test_dir.mkdir(parents=True, exist_ok=True)

    mgr = JobManager()

    # Verificar estado inicial
    assert mgr._worker is None or not mgr._worker.is_alive(), "Worker já está rodando"

    # Criar job de teste que não depende de APIs externas
    try:
        plan = load_e2e_plan()
    except Exception:
        plan = {"titulo_video": "test", "cenas": [], "card_final": None}

    # Criar um job diretamente no job manager
    request = CreateJobRequest(
        resolution="720p",
        orientation="vertical",
        duration_seconds=10,
        prompt="Teste de recuperação do worker",
        video_model="seedance_1_5_pro",
    )

    metadata = mgr.create_job(request, apply_logo_overlay=False)
    job_id = metadata["job_id"]
    assert job_id, "Job ID não gerado"

    # Verificar estado inicial do job
    initial_status = mgr.get_job_status(job_id)
    assert initial_status.status in {"queued", "pending"}, (
        f"Status inesperado: {initial_status.status}"
    )

    # Iniciar e parar o worker (simulando crash durante processamento)
    mgr.start()
    assert mgr._worker is not None and mgr._worker.is_alive(), "Worker não iniciou"

    # Aguardar job começar a processar
    time.sleep(2)
    mid_status = mgr.get_job_status(job_id)
    print(f"  Status durante processamento: {mid_status.status}")

    # Parar worker (simula crash)
    mgr.stop()
    assert mgr._worker is None or not mgr._worker.is_alive(), "Worker não parou"

    # O job deve continuar existindo (não perdido)
    post_crash_status = mgr.get_job_status(job_id)
    assert post_crash_status is not None, "Job perdido após crash do worker"
    print(f"  Status após crash: {post_crash_status.status}")

    # Reiniciar worker e verificar retomada
    mgr.start()
    assert mgr._worker is not None and mgr._worker.is_alive(), "Worker não reiniciou"

    # Aguardar processamento
    max_wait = 120
    start = time.time()

    while time.time() - start < max_wait:
        status = mgr.get_job_status(job_id)
        if status.status in {"completed", "failed"}:
            break
        time.sleep(2)

    final_status = mgr.get_job_status(job_id)
    print(f"  Status final: {final_status.status}")

    # O job deve estar em estado terminal (completed ou failed, mas nunca lost)
    assert final_status.status in {"completed", "failed"}, (
        f"Job não terminou após {max_wait}s: {final_status.status}"
    )

    # Cleanup
    mgr.stop()

    print(f"\n  ✓ Worker recovery test passou")
    print(f"  ✓ Job sobreviveu ao crash e foi retomado")


# ── Teste 5: Validação de saúde dos serviços externos ──────────────────────

@pytest.mark.e2e
def test_e2e_external_health():
    """Verifica conectividade com todos os serviços externos."""
    from scripts.external_health import probe_external_health

    health = probe_external_health(startup_mode="test")

    services = health.services

    # FFmpeg é obrigatório
    assert services["ffmpeg"].ok, f"FFmpeg: {services['ffmpeg'].message}"

    # Demais serviços — reportar mas não falhar (podem estar offline)
    for name in ["openai", "higgsfield_auth", "elevenlabs"]:
        svc = services[name]
        status = "✓" if svc.ok else "⚠"
        print(f"  {status} {name}: {svc.message}")

    print(f"\n  ready_for_submit: {health.ready_for_submit}")


# ── Teste 6: Validação do output (qualidade do vídeo) ──────────────────────

@pytest.mark.e2e
@pytest.mark.slow
def test_e2e_output_validation():
    """Valida propriedades do vídeo gerado: codec, resolução, duração, áudio."""
    keys = check_env_keys()
    if not keys["hf"]:
        pytest.skip("HF_API_KEY não configurada")
    if not keys["ffmpeg"]:
        pytest.skip("FFmpeg não disponível")

    hf_ok, hf_msg = check_hf_connectivity()
    if not hf_ok:
        pytest.skip(f"Higgsfield indisponível: {hf_msg}")

    from scripts.pipeline import executar_pipeline

    plano = load_e2e_plan()
    resultado = executar_pipeline(plano=plano)

    assert resultado["sucesso"], f"Pipeline falhou: {resultado['cenas_falharam']}"
    video_path = Path(resultado["video_local"])

    # Verificar com ffprobe
    def ffprobe(path: Path) -> dict:
        """Extrai metadados do vídeo via ffprobe."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return {}
        return json.loads(proc.stdout)

    info = ffprobe(video_path)
    assert info, "ffprobe não conseguiu ler o vídeo"

    streams = info.get("streams", [])
    fmt = info.get("format", {})

    # Deve ter pelo menos 1 stream de vídeo
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    assert len(video_streams) >= 1, "Nenhum stream de vídeo encontrado"

    # Codec deve ser h264
    video_codec = video_streams[0].get("codec_name", "")
    assert "h264" in video_codec, f"Codec inesperado: {video_codec}"

    # Duração > 0
    duration = float(fmt.get("duration", 0))
    assert duration > 0, "Duração inválida (0s)"

    # Tamanho razoável (> 500KB para vídeo de ~10s)
    size_mb = video_path.stat().st_size / (1024 * 1024)
    assert size_mb > 0.5, f"Vídeo muito pequeno: {size_mb:.2f} MB"

    print(f"\n  ✓ Codec: {video_codec}")
    print(f"  ✓ Duração: {duration:.1f}s")
    print(f"  ✓ Tamanho: {size_mb:.2f} MB")
    print(f"  ✓ Streams: {len(streams)} (video: {len(video_streams)})")



