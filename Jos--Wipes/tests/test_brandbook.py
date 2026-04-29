"""Valida config/brandbook.json: estrutura, campos obrigatórios, consistência e tamanho."""

import sys
import json
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from scripts.config import CONFIG_DIR


def main():
    print("=" * 50)
    print("TESTE: Brandbook JSON")
    print("=" * 50)

    path = CONFIG_DIR / "brandbook.json"

    # [1/4] JSON válido
    print("\n[1/4] Verificando JSON válido...")
    try:
        with open(path, "r", encoding="utf-8") as f:
            bb = json.load(f)
        print(f"  ✓ JSON válido")
    except FileNotFoundError:
        print(f"  ✗ Arquivo não encontrado: {path}")
        return 1
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON inválido: {e}")
        return 1

    erros = 0

    # [2/4] Campos obrigatórios (12+)
    print("\n[2/4] Verificando campos obrigatórios...")
    campos = [
        "meta", "marca", "produto", "identidade_visual", "tom_de_voz",
        "publico_alvo", "mensagens_chave", "ocasioes_consumo",
        "formatos_video", "direcoes_cinematograficas", "composicao_final",
        "restricoes"
    ]
    for campo in campos:
        if campo in bb and bb[campo]:
            print(f"  ✓ {campo}")
        else:
            print(f"  ✗ {campo} — ausente ou vazio")
            erros += 1

    print(f"  {len(campos)} campos verificados")

    # [3/4] Consistência
    print("\n[3/4] Verificando consistência...")

    # Paleta preto/branco
    paleta = bb.get("identidade_visual", {}).get("paleta", {}).get("primarias", [])
    if "#000000" in paleta and "#FFFFFF" in paleta:
        print("  ✓ Paleta é preto e branco")
    else:
        print(f"  ✗ Paleta deveria ser preto/branco: {paleta}")
        erros += 1

    # Aspect ratio 9:16
    formato = bb.get("direcoes_cinematograficas", {}).get("formato", "")
    if "9:16" in formato:
        print("  ✓ Aspect ratio 9:16")
    else:
        print(f"  ✗ Formato deveria ser 9:16: {formato}")
        erros += 1

    # >= 3 formatos
    formatos = bb.get("formatos_video", [])
    if len(formatos) >= 3:
        print(f"  ✓ {len(formatos)} formatos de vídeo (≥3)")
    else:
        print(f"  ✗ Apenas {len(formatos)} formatos (mín 3)")
        erros += 1

    # >= 3 ocasiões
    ocasioes = bb.get("ocasioes_consumo", [])
    if len(ocasioes) >= 3:
        print(f"  ✓ {len(ocasioes)} ocasiões de consumo (≥3)")
    else:
        print(f"  ✗ Apenas {len(ocasioes)} ocasiões (mín 3)")
        erros += 1

    # Ocasiões com prompt em inglês
    ocasioes_com_prompt = sum(1 for o in ocasioes if o.get("cenario_prompt"))
    if ocasioes_com_prompt == len(ocasioes):
        print(f"  ✓ Todas as ocasiões têm cenário prompt em inglês")
    else:
        print(f"  ✗ {ocasioes_com_prompt}/{len(ocasioes)} ocasiões têm prompt")
        erros += 1

    # Personagens grupo de apoio >= 3
    ga = next((f for f in formatos if f.get("id") == "grupo_de_apoio"), None)
    if ga:
        personagens = ga.get("personagens", [])
        if len(personagens) >= 3:
            print(f"  ✓ {len(personagens)} personagens no grupo de apoio (≥3)")
        else:
            print(f"  ✗ Apenas {len(personagens)} personagens (mín 3)")
            erros += 1
    else:
        print("  ✗ Formato 'grupo_de_apoio' não encontrado")
        erros += 1

    # [4/4] Tamanho em tokens
    print("\n[4/4] Estimando tamanho...")
    texto = json.dumps(bb, ensure_ascii=False)
    chars = len(texto)
    tokens_est = chars // 4  # estimativa grosseira: 1 token ~ 4 chars
    print(f"  Caracteres: {chars}")
    print(f"  Tokens estimados: ~{tokens_est}")

    if tokens_est < 10000:
        print(f"  ✓ Cabe no contexto do Claude (<10k tokens)")
    else:
        print(f"  ✗ Muito grande para o contexto ({tokens_est} tokens)")
        erros += 1

    # Resultado
    if erros > 0:
        print(f"\n{'=' * 50}")
        print(f"  ✗ TESTE BRANDBOOK: FALHOU ({erros} erros)")
        return 1

    print(f"\n{'=' * 50}")
    print("  ✓ TESTE BRANDBOOK: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
