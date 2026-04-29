"""Sistema de gerenciamento de vozes para José Wipes Pipeline."""

import sys
import json
import argparse
import time
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.config import (
    ELEVENLABS_API_KEY, CONFIG_DIR, OUTPUT_DIR, ASSETS_DIR, gerar_audio
)


VOZES_FILE = CONFIG_DIR / "vozes.json"


def carregar():
    with open(VOZES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar(data):
    with open(VOZES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_client():
    from elevenlabs.client import ElevenLabs
    return ElevenLabs(api_key=ELEVENLABS_API_KEY)


def cmd_listar():
    """Lista todas as vozes na conta ElevenLabs."""
    print("\n=== Vozes na conta ElevenLabs ===\n")
    client = get_client()
    response = client.voices.get_all()
    voices = response.voices if hasattr(response, "voices") else response

    print(f"{'Nome':<30} {'ID':<25} {'Categoria'}")
    print("-" * 80)
    for v in voices:
        cat = v.category if hasattr(v, "category") else "?"
        print(f"  {v.name:<28} {v.voice_id:<25} {cat}")
    print(f"\nTotal: {len(voices)} vozes")


def cmd_catalogo():
    """Busca vozes masculinas no catálogo público."""
    print("\n=== Vozes Masculinas no Catálogo ===\n")
    client = get_client()
    response = client.voices.get_all()
    voices = response.voices if hasattr(response, "voices") else response

    masculinas = []
    for v in voices:
        labels = v.labels or {}
        if labels.get("gender") == "male":
            masculinas.append(v)

    if not masculinas:
        print("  Nenhuma voz masculina encontrada. Mostrando todas:")
        masculinas = voices[:10]

    print(f"{'Nome':<25} {'ID':<25} {'Sotaque':<15} {'Idade'}")
    print("-" * 80)
    for v in masculinas[:20]:
        labels = v.labels or {}
        sotaque = labels.get("accent", "?")
        idade = labels.get("age", "?")
        print(f"  {v.name:<23} {v.voice_id:<25} {sotaque:<15} {idade}")
    print(f"\nTotal masculinas: {len(masculinas)}")


def cmd_placeholder(persona, voice_id):
    """Registra uma voz do catálogo como placeholder."""
    data = carregar()
    if persona not in data:
        print(f"  Persona '{persona}' não existe. Use: narrador, joao, lider")
        return

    data[persona]["voice_id"] = voice_id
    data[persona]["tipo"] = "placeholder"
    salvar(data)
    print(f"  ✓ Voz {voice_id} registrada como placeholder para '{persona}'")


def cmd_clonar(persona):
    """Clona voz a partir de amostras em assets/vozes/<persona>/."""
    data = carregar()
    if persona not in data:
        print(f"  Persona '{persona}' não existe.")
        return

    pasta = ASSETS_DIR / "vozes" / persona
    amostras = list(pasta.glob("*.wav")) + list(pasta.glob("*.mp3")) + list(pasta.glob("*.m4a"))

    if not amostras:
        print(f"  Nenhuma amostra encontrada em {pasta}")
        print(f"  Coloque arquivos WAV/MP3/M4A nessa pasta e tente novamente.")
        return

    print(f"  Encontradas {len(amostras)} amostras: {[a.name for a in amostras]}")

    client = get_client()
    try:
        voice = client.clone(
            name=f"josewipes_{persona}",
            files=[str(a) for a in amostras],
            description=data[persona].get("descricao", ""),
        )
        data[persona]["voice_id"] = voice.voice_id
        data[persona]["tipo"] = "clonada"
        salvar(data)
        print(f"  ✓ Voz clonada! ID: {voice.voice_id}")
    except Exception as e:
        print(f"  ✗ Erro na clonagem: {e}")


def cmd_testar(persona):
    """Testa uma voz gerando áudio curto e longo."""
    data = carregar()
    if persona not in data:
        print(f"  Persona '{persona}' não existe.")
        return

    voz = data[persona]
    if not voz.get("voice_id"):
        print(f"  ✗ voice_id não configurado para '{persona}'. Use --placeholder ou --clonar.")
        return

    textos = voz.get("textos_teste", {})

    for tipo, texto in textos.items():
        print(f"\n  Gerando áudio {tipo} para '{persona}'...")
        out_path = OUTPUT_DIR / f"teste_voz_{persona}_{tipo}.mp3"
        ok = gerar_audio(persona, texto, out_path)
        if ok:
            print(f"  ✓ {tipo}: {out_path}")
        else:
            print(f"  ✗ {tipo}: falhou")

    # Pedir score
    try:
        print(f"\n  Avalie a voz '{persona}' (0-5):")
        score = int(input("  Score: ").strip())
        notas = input("  Notas: ").strip()
        data[persona]["score"] = score
        data[persona]["score_notas"] = notas
        salvar(data)
        print(f"  ✓ Score atualizado: {score}")
    except (ValueError, EOFError):
        print("  Score não registrado.")


def cmd_testar_todas():
    """Testa todas as vozes configuradas."""
    data = carregar()
    for persona in ["narrador", "joao", "lider"]:
        if data.get(persona, {}).get("voice_id"):
            print(f"\n{'=' * 40}")
            print(f"Testando: {persona}")
            cmd_testar(persona)
        else:
            print(f"\n  {persona}: sem voice_id, pulando")


def cmd_status():
    """Mostra status de todas as personas."""
    data = carregar()
    print("\n=== Status das Vozes ===\n")
    print(f"{'Persona':<12} {'Nome':<25} {'Tipo':<12} {'Voice ID':<15} {'Score'}")
    print("-" * 75)

    for persona in ["narrador", "joao", "lider"]:
        voz = data.get(persona, {})
        nome = voz.get("nome", "?")
        tipo = voz.get("tipo", "?")
        vid = voz.get("voice_id", "")
        vid_display = vid[:12] + "..." if vid else "nao config"
        score = voz.get("score", 0)
        icon = "✓" if vid else "✗"
        print(f"  {icon} {persona:<10} {nome:<25} {tipo:<12} {vid_display:<15} {score}")


def main():
    parser = argparse.ArgumentParser(description="Gerenciador de vozes José Wipes")
    parser.add_argument("--listar", action="store_true", help="Lista vozes na conta")
    parser.add_argument("--catalogo", action="store_true", help="Busca vozes masculinas")
    parser.add_argument("--placeholder", nargs=2, metavar=("PERSONA", "VOICE_ID"), help="Registra placeholder")
    parser.add_argument("--clonar", type=str, metavar="PERSONA", help="Clona voz")
    parser.add_argument("--testar", type=str, metavar="PERSONA", help="Testa voz")
    parser.add_argument("--testar-todas", action="store_true", help="Testa todas")
    parser.add_argument("--status", action="store_true", help="Mostra status")
    args = parser.parse_args()

    if args.listar:
        cmd_listar()
    elif args.catalogo:
        cmd_catalogo()
    elif args.placeholder:
        cmd_placeholder(args.placeholder[0], args.placeholder[1])
    elif args.clonar:
        cmd_clonar(args.clonar)
    elif args.testar:
        cmd_testar(args.testar)
    elif args.testar_todas:
        cmd_testar_todas()
    else:
        cmd_status()


if __name__ == "__main__":
    main()
