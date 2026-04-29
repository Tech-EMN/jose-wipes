"""Diagnostico rapido do sistema - nao gasta creditos de API."""

import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.config import (
    CONFIG_DIR,
    ELEVENLABS_API_KEY,
    GOOGLE_DRIVE_FOLDER_ID,
    GOOGLE_SERVICE_ACCOUNT_FILE,
    HF_API_KEY,
    HF_API_SECRET,
    OPENAI_API_KEY,
    OPENAI_PLANNER_MODEL,
    PROJECT_ROOT,
    obter_path_imagem_produto,
)
from scripts.openai_utils import create_text_response


def check_env():
    """1. Variaveis de ambiente."""

    chaves = {
        "HF_API_KEY": HF_API_KEY,
        "HF_API_SECRET": HF_API_SECRET,
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "ELEVENLABS_API_KEY": ELEVENLABS_API_KEY,
        "GOOGLE_SERVICE_ACCOUNT_FILE": GOOGLE_SERVICE_ACCOUNT_FILE,
        "GOOGLE_DRIVE_FOLDER_ID": GOOGLE_DRIVE_FOLDER_ID,
    }
    ok = all(v and not v.startswith("your_") for v in chaves.values())
    faltam = [k for k, v in chaves.items() if not v or v.startswith("your_")]
    return ok, f"Faltam: {', '.join(faltam)}" if faltam else "Todas configuradas"


def check_deps():
    """2. Dependencias Python."""

    deps = [
        "dotenv",
        "anthropic",
        "openai",
        "elevenlabs",
        "higgsfield_client",
        "googleapiclient",
        "httpx",
    ]
    faltam = []
    for dep in deps:
        try:
            __import__(dep)
        except ImportError:
            faltam.append(dep)
    ok = len(faltam) == 0
    return ok, f"Faltam: {', '.join(faltam)}" if faltam else "Todas instaladas"


def check_ffmpeg():
    """3. FFmpeg."""

    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        versao = result.stdout.split("\n")[0]
        return True, versao
    except FileNotFoundError:
        return False, "FFmpeg nao instalado"


def check_configs():
    """4. Arquivos de configuracao."""

    arquivos = ["brandbook.json", "prompts_library.json"]
    faltam = [a for a in arquivos if not (CONFIG_DIR / a).exists()]
    env_ok = (PROJECT_ROOT / ".env").exists()
    if not env_ok:
        faltam.append(".env")
    ok = len(faltam) == 0
    return ok, f"Faltam: {', '.join(faltam)}" if faltam else "Todos presentes"


def check_higgsfield():
    """5. API Higgsfield (valida auth basica via upload da referencia oficial)."""

    if not HF_API_KEY or HF_API_KEY.startswith("your_"):
        return False, "API key nao configurada"
    try:
        import higgsfield_client

        product_path = obter_path_imagem_produto(strict=True)
        url = higgsfield_client.upload_file(str(product_path))
        if url and str(url).startswith("http"):
            return True, "Upload autenticado da referencia do produto OK (auth basica confirmada)"
        return False, f"Upload retornou valor inesperado: {url}"
    except ImportError:
        return False, "higgsfield_client nao instalado"
    except Exception as e:
        return False, f"Erro: {e}"


def check_elevenlabs():
    """6. API ElevenLabs."""

    if not ELEVENLABS_API_KEY or ELEVENLABS_API_KEY.startswith("your_"):
        return False, "API key nao configurada"
    try:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        response = client.voices.get_all()
        voices = response.voices if hasattr(response, "voices") else response
        return True, f"{len(voices)} vozes disponiveis"
    except Exception as e:
        return False, f"Erro: {e}"


def check_openai():
    """7. API OpenAI."""

    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("your_"):
        return False, "API key nao configurada"
    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        text = create_text_response(
            client=client,
            model=OPENAI_PLANNER_MODEL,
            instructions="Responda de forma minima.",
            user_input="Responda ok",
            max_output_tokens=200,
        )
        return True, f"{OPENAI_PLANNER_MODEL}: {text}"
    except Exception as e:
        return False, f"Erro: {e}"


def check_disco():
    """8. Espaco em disco."""

    total, used, free = shutil.disk_usage(str(PROJECT_ROOT))
    free_gb = free / (1024**3)
    ok = free_gb >= 5
    return ok, f"{free_gb:.1f} GB livres"


def main():
    print("\n" + "=" * 60)
    print("  HEALTH CHECK - Jose Wipes Pipeline")
    print("=" * 60)

    checks = [
        ("1. Variaveis de ambiente", check_env),
        ("2. Dependencias Python", check_deps),
        ("3. FFmpeg", check_ffmpeg),
        ("4. Arquivos de config", check_configs),
        ("5. API Higgsfield (auth basica)", check_higgsfield),
        ("6. API ElevenLabs", check_elevenlabs),
        ("7. API OpenAI", check_openai),
        ("8. Espaco em disco", check_disco),
    ]

    resultados = []
    for nome, check_fn in checks:
        print(f"\n  {nome}...")
        try:
            ok, msg = check_fn()
        except Exception as e:
            ok, msg = False, f"Erro inesperado: {e}"

        icon = "+" if ok else "x"
        print(f"    {icon} {msg}")
        resultados.append((nome, ok, msg))

    total = len(resultados)
    passou = sum(1 for _, ok, _ in resultados if ok)

    print(f"\n{'=' * 60}")
    if passou == total:
        print(f"  [+] Integracoes basicas OK ({passou}/{total})")
        print("      Observacao: Higgsfield aqui valida auth/upload, nao prova render completo.")
    elif passou >= total - 2:
        print(f"  [~] Funcional com limitacoes ({passou}/{total})")
        for nome, ok, msg in resultados:
            if not ok:
                print(f"      x {nome}: {msg}")
    else:
        print(f"  [-] Problemas detectados ({passou}/{total})")
        for nome, ok, msg in resultados:
            if not ok:
                print(f"      x {nome}: {msg}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
