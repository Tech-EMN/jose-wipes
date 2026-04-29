"""Testa conexão e geração de áudio com ElevenLabs."""

import sys
import time
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from scripts.config import ELEVENLABS_API_KEY, OUTPUT_DIR


def main():
    print("=" * 50)
    print("TESTE: ElevenLabs — Geração de Áudio")
    print("=" * 50)

    # [1/4] Validar config
    print("\n[1/4] Validando configuração...")
    if not ELEVENLABS_API_KEY or ELEVENLABS_API_KEY.startswith("your_"):
        print("  ✗ ELEVENLABS_API_KEY não configurado no .env")
        return 1
    print("  ✓ API key encontrada")

    # [2/4] Conectar e listar vozes
    print("\n[2/4] Conectando e listando vozes...")
    try:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        response = client.voices.get_all()
        voices = response.voices if hasattr(response, "voices") else response

        print(f"  ✓ {len(voices)} vozes disponíveis. Primeiras 5:")
        voz_masculina = None
        for v in voices[:5]:
            labels = v.labels or {}
            genero = labels.get("gender", "?")
            print(f"    - {v.name} (ID: {v.voice_id}, género: {genero})")
            if genero == "male" and not voz_masculina:
                voz_masculina = v

        if not voz_masculina:
            # Fallback: usar primeira voz
            voz_masculina = voices[0]
            print(f"  (usando primeira voz como fallback: {voz_masculina.name})")

    except Exception as e:
        print(f"  ✗ Erro ao listar vozes: {e}")
        return 1

    # [3/4] Gerar áudio
    print(f"\n[3/4] Gerando áudio com voz '{voz_masculina.name}'...")
    texto = "José Wipes. A recuperação que você merece."
    print(f"  Texto: {texto}")

    inicio = time.time()
    try:
        from elevenlabs import VoiceSettings

        audio = client.text_to_speech.convert(
            voice_id=voz_masculina.voice_id,
            text=texto,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
            voice_settings=VoiceSettings(
                stability=0.7,
                similarity_boost=0.85,
                style=0.15,
            ),
        )

        # [4/4] Salvar
        out_path = OUTPUT_DIR / "teste_elevenlabs.mp3"
        with open(out_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)

        duracao = time.time() - inicio
        tamanho = out_path.stat().st_size / 1024

        print(f"\n[4/4] Resultado:")
        print(f"  ✓ Arquivo: {out_path}")
        print(f"  ✓ Tamanho: {tamanho:.1f} KB")
        print(f"  ✓ Tempo de geração: {duracao:.1f}s")

    except Exception as e:
        print(f"  ✗ Erro ao gerar áudio: {e}")
        return 1

    print(f"\n{'=' * 50}")
    print("  ✓ TESTE ELEVENLABS: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
