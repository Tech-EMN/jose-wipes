"""
Configuração central do projeto José Wipes Pipeline.
Carrega variáveis de ambiente, define paths e funções utilitárias.
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

from scripts.product_reference import (
    detectar_gatilhos_referencia_produto,
    obter_imagem_produto_path,
    prompt_pede_referencia_produto,
)
from scripts.openai_utils import create_text_response

# Fix Windows console encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

# Paths do projeto
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
ASSETS_DIR = PROJECT_ROOT / "assets"
OUTPUT_DIR = PROJECT_ROOT / "output"
CONFIG_DIR = PROJECT_ROOT / "config"
LOGS_DIR = PROJECT_ROOT / "logs"
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
PRODUCT_IMAGE_PATH = obter_imagem_produto_path()

# Carregar .env
load_dotenv(PROJECT_ROOT / ".env")

# API Keys
HF_API_KEY = os.getenv("HF_API_KEY", "")
HF_API_SECRET = os.getenv("HF_API_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_PLANNER_MODEL = os.getenv("OPENAI_PLANNER_MODEL", "gpt-5.4-pro")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

# Garantir que diretórios existem
for d in [ASSETS_DIR, OUTPUT_DIR, OUTPUT_DIR / "cenas", OUTPUT_DIR / "final",
          CONFIG_DIR, LOGS_DIR, CREDENTIALS_DIR,
          ASSETS_DIR / "logo", ASSETS_DIR / "vozes" / "narrador",
          ASSETS_DIR / "vozes" / "joao", ASSETS_DIR / "vozes" / "lider",
          ASSETS_DIR / "referencias"]:
    d.mkdir(parents=True, exist_ok=True)


def validar_configuracao():
    """Verifica se todas as chaves de API estão preenchidas."""
    chaves = {
        "HF_API_KEY": HF_API_KEY,
        "HF_API_SECRET": HF_API_SECRET,
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "ELEVENLABS_API_KEY": ELEVENLABS_API_KEY,
        "GOOGLE_SERVICE_ACCOUNT_FILE": GOOGLE_SERVICE_ACCOUNT_FILE,
        "GOOGLE_DRIVE_FOLDER_ID": GOOGLE_DRIVE_FOLDER_ID,
    }

    print("=" * 50)
    print("VALIDAÇÃO DE CONFIGURAÇÃO — José Wipes Pipeline")
    print("=" * 50)

    todas_ok = True
    for nome, valor in chaves.items():
        if valor and not valor.startswith("your_"):
            status = "✓"
        else:
            status = "✗"
            todas_ok = False
        print(f"  {status} {nome}: {'configurado' if status == '✓' else 'NÃO CONFIGURADO'}")

    print("-" * 50)
    print(f"  PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"  ASSETS_DIR:   {ASSETS_DIR}")
    print(f"  OUTPUT_DIR:   {OUTPUT_DIR}")
    print(f"  CONFIG_DIR:   {CONFIG_DIR}")
    print(f"  LOGS_DIR:     {LOGS_DIR}")
    print("-" * 50)

    if todas_ok:
        print("  ✓ Todas as configurações estão OK!")
    else:
        print("  ✗ Edite o arquivo .env com suas chaves reais.")

    return todas_ok


def carregar_brandbook():
    """Retorna o dict do brandbook.json."""
    path = CONFIG_DIR / "brandbook.json"
    if not path.exists():
        print(f"  ✗ Brandbook não encontrado em {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def obter_logo_path() -> Path:
    """Retorna o path do logo da marca com fallback para variantes do nome do arquivo."""
    candidatos = [
        ASSETS_DIR / "logo" / "logo_jose_wipes.png",
        ASSETS_DIR / "logo" / "Logo_josé_wipes.png",
        ASSETS_DIR / "logo" / "logo_josé_wipes.png",
    ]
    for candidato in candidatos:
        if candidato.exists():
            return candidato
    return candidatos[0]


def obter_path_imagem_produto(*, strict: bool = False) -> Path:
    """Retorna o path da imagem oficial do produto com fallback para variantes de nome."""

    return obter_imagem_produto_path(strict=strict)


def brandbook_para_contexto():
    """Retorna versão compacta do brandbook como string JSON para injetar no system prompt."""
    bb = carregar_brandbook()
    if not bb:
        return "{}"
    # Campos relevantes para geração
    campos = ["marca", "produto", "identidade_visual", "tom_de_voz",
              "publico_alvo", "mensagens_chave", "ocasioes_consumo",
              "formatos_video", "direcoes_cinematograficas",
              "composicao_final", "restricoes"]
    compacto = {k: bb[k] for k in campos if k in bb}
    return json.dumps(compacto, ensure_ascii=False, indent=2)


def carregar_vozes():
    """Retorna dict de vozes do config/vozes.json."""
    path = CONFIG_DIR / "vozes.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def gerar_audio(persona, texto, output_path):
    """Gera áudio MP3 usando ElevenLabs com os settings da persona. Retorna True/False."""
    try:
        from elevenlabs.client import ElevenLabs

        vozes = carregar_vozes()
        if persona not in vozes:
            print(f"  ✗ Persona '{persona}' não encontrada em vozes.json")
            return False

        voz_config = vozes[persona]
        voice_id = voz_config.get("voice_id")
        if not voice_id:
            print(f"  ✗ voice_id não configurado para '{persona}'")
            return False

        settings = voz_config.get("settings", {})

        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

        from elevenlabs import VoiceSettings
        voice_settings = VoiceSettings(
            stability=settings.get("stability", 0.5),
            similarity_boost=settings.get("similarity_boost", 0.75),
            style=settings.get("style", 0.0),
        )

        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=texto,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
            voice_settings=voice_settings,
        )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)

        print(f"  ✓ Áudio gerado: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")
        return True

    except Exception as e:
        print(f"  ✗ Erro ao gerar áudio para '{persona}': {e}")
        return False


_product_image_url_cache = None


def obter_url_imagem_produto() -> str:
    """
    Faz upload da imagem da embalagem para a Higgsfield e retorna URL pública.
    Cacheia o resultado para não fazer upload toda vez.
    A URL é usada como referência em todas as gerações que envolvem o produto.
    """
    global _product_image_url_cache
    product_image_path = obter_path_imagem_produto(strict=True)

    if (
        _product_image_url_cache
        and getattr(obter_url_imagem_produto, "_cached_path", None) == str(product_image_path)
    ):
        return _product_image_url_cache

    import higgsfield_client

    url = higgsfield_client.upload_file(str(product_image_path))
    _product_image_url_cache = url
    obter_url_imagem_produto._cached_path = str(product_image_path)
    return url


def decompor_briefing(briefing: str) -> dict:
    """Chama OpenAI GPT com o system prompt montado, parseia JSON, retorna o plano."""
    try:
        from openai import OpenAI
        from scripts.system_prompt import montar_system_prompt

        client = OpenAI(api_key=OPENAI_API_KEY)
        system = montar_system_prompt()

        resposta = create_text_response(
            client=client,
            model=OPENAI_PLANNER_MODEL,
            instructions=system,
            user_input=briefing,
            max_output_tokens=12000,
        )
        resposta = resposta.strip()
        # Limpar possível markdown
        if resposta.startswith("```"):
            resposta = resposta.split("\n", 1)[1]
            if resposta.endswith("```"):
                resposta = resposta[:-3]
            resposta = resposta.strip()

        plano = json.loads(resposta)
        return plano

    except json.JSONDecodeError as e:
        print(f"  ✗ Erro ao parsear JSON: {e}")
        print(f"  Resposta bruta: {resposta[:500]}")
        return {}
    except Exception as e:
        print(f"  ✗ Erro ao decompor briefing: {e}")
        return {}


if __name__ == "__main__":
    validar_configuracao()
