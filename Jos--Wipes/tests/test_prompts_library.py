"""Valida config/prompts_library.json: estrutura, IDs únicos, idioma dos prompts."""

import sys
import json
import re
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from scripts.config import CONFIG_DIR


def main():
    print("=" * 50)
    print("TESTE: Prompts Library JSON")
    print("=" * 50)

    path = CONFIG_DIR / "prompts_library.json"

    # [1/4] JSON válido
    print("\n[1/4] Verificando JSON válido...")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print("  ✓ JSON válido")
    except Exception as e:
        print(f"  ✗ Erro: {e}")
        return 1

    erros = 0
    todos = []

    # Coletar todos os prompts
    for cat, itens in data.get("video", {}).items():
        todos.extend(itens)
    todos.extend(data.get("imagem", []))

    print(f"  Total: {len(todos)} prompts")

    # [2/4] Campos obrigatórios
    print("\n[2/4] Verificando campos obrigatórios...")
    campos_obrigatorios = ["id", "nome", "prompt", "modelo_recomendado", "parametros", "score"]
    for p in todos:
        for campo in campos_obrigatorios:
            if campo not in p:
                print(f"  ✗ {p.get('id', '???')}: campo '{campo}' ausente")
                erros += 1
    if erros == 0:
        print(f"  ✓ Todos os {len(todos)} prompts têm campos obrigatórios")

    # [3/4] IDs únicos
    print("\n[3/4] Verificando IDs únicos...")
    ids = [p["id"] for p in todos]
    duplicados = set(i for i in ids if ids.count(i) > 1)
    if duplicados:
        print(f"  ✗ IDs duplicados: {duplicados}")
        erros += len(duplicados)
    else:
        print(f"  ✓ Todos os {len(ids)} IDs são únicos")

    # [4/4] Prompts em inglês
    print("\n[4/4] Verificando idioma dos prompts...")
    palavras_pt = ["de", "para", "que", "com", "uma", "não", "está", "são", "ele"]
    palavras_en = ["the", "with", "and", "in", "of", "from", "light", "camera", "shot"]

    for p in todos:
        texto = p.get("prompt", "").lower()
        pt_count = sum(1 for w in palavras_pt if f" {w} " in texto)
        en_count = sum(1 for w in palavras_en if f" {w} " in texto)

        if pt_count > en_count and pt_count > 3:
            print(f"  ✗ {p['id']}: prompt parece estar em português (PT:{pt_count} vs EN:{en_count})")
            erros += 1

    if erros == 0:
        print(f"  ✓ Todos os prompts parecem estar em inglês")

    # Resultado
    if erros > 0:
        print(f"\n{'=' * 50}")
        print(f"  ✗ TESTE PROMPTS LIBRARY: FALHOU ({erros} erros)")
        return 1

    print(f"\n{'=' * 50}")
    print("  ✓ TESTE PROMPTS LIBRARY: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
