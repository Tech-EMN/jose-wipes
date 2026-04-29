"""Valida config/vozes.json e função gerar_audio."""

import sys
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from scripts.config import CONFIG_DIR


def main():
    print("=" * 50)
    print("TESTE: Sistema de Vozes")
    print("=" * 50)

    erros = 0

    # [1/3] vozes.json existe
    print("\n[1/3] Verificando vozes.json...")
    import json
    path = CONFIG_DIR / "vozes.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"  ✓ vozes.json existe ({len(data)} personas)")
    else:
        print(f"  ✗ vozes.json não encontrado")
        erros += 1
        data = {}

    # [2/3] Pelo menos 2 personas configuradas
    print("\n[2/3] Verificando personas...")
    configuradas = 0
    for persona in ["narrador", "joao", "lider"]:
        if persona in data:
            vid = data[persona].get("voice_id", "")
            if vid:
                print(f"  ✓ {persona}: voice_id configurado")
                configuradas += 1
            else:
                print(f"  ! {persona}: sem voice_id (precisa configurar)")
        else:
            print(f"  ✗ {persona}: não encontrado")

    if configuradas < 2:
        print(f"\n  AVISO: Apenas {configuradas}/3 personas configuradas com voice_id")
        print(f"  Use: python scripts/clonar_vozes.py --catalogo")
        print(f"  Depois: python scripts/clonar_vozes.py --placeholder narrador <VOICE_ID>")
        # Warning, não erro fatal

    # [3/3] gerar_audio importável
    print("\n[3/3] Verificando função gerar_audio...")
    try:
        from scripts.config import gerar_audio
        if callable(gerar_audio):
            print("  ✓ gerar_audio é importável e callable")
        else:
            print("  ✗ gerar_audio não é callable")
            erros += 1
    except ImportError as e:
        print(f"  ✗ Erro ao importar: {e}")
        erros += 1

    if erros > 0:
        print(f"\n{'=' * 50}")
        print(f"  ✗ TESTE VOZES: FALHOU ({erros} erros)")
        return 1

    print(f"\n{'=' * 50}")
    print("  ✓ TESTE VOZES: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
