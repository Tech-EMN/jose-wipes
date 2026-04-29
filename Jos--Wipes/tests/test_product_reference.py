"""Valida a política central de referência da embalagem/produto."""

import sys
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from scripts.product_reference import (
    aplicar_regra_referencia_produto_plano,
    detectar_gatilhos_referencia_produto,
    obter_imagem_produto_path,
    prompt_pede_referencia_produto,
    scene_dict_pede_referencia_produto,
)


def main():
    print("=" * 50)
    print("TESTE: Product Reference Policy")
    print("=" * 50)

    image_path = obter_imagem_produto_path()
    if not image_path.exists():
        print(f"  ✗ Imagem oficial não encontrada: {image_path}")
        return 1

    triggers = detectar_gatilhos_referencia_produto(
        "Quero mostrar a embalagem do lenço umedecido no final."
    )
    if not triggers:
        print("  ✗ Os gatilhos de embalagem não foram detectados")
        return 1

    if not prompt_pede_referencia_produto("Use o produto José Wipes no anúncio."):
        print("  ✗ O prompt com produto deveria exigir referência visual")
        return 1

    if prompt_pede_referencia_produto("Quero um anúncio engraçado sobre banheiro de aeroporto."):
        print("  ✗ Um prompt neutro não deveria forçar a referência do produto")
        return 1

    scene = {
        "titulo": "Reveal",
        "prompt": "Hero shot showing the wipes package on a dark premium surface.",
    }
    if not scene_dict_pede_referencia_produto(scene):
        print("  ✗ A cena com package/wipes deveria pedir referência")
        return 1

    plano = {
        "titulo_video": "Teste",
        "cenas": [
            {"titulo": "Cena 1", "prompt": "A man enters a public bathroom."},
            {"titulo": "Cena 2", "prompt": "He looks relieved and confident."},
        ],
    }
    aplicar_regra_referencia_produto_plano(
        plano,
        briefing="No último shot, mostrar a embalagem do lenço umedecido.",
    )
    last_overlay = plano["cenas"][-1].get("produto_overlay", {})
    if not last_overlay.get("ativo"):
        print("  ✗ O plano deveria forçar produto_overlay na última cena")
        return 1

    print("  ✓ Resolver, gatilhos e plano legado estão consistentes")
    print("-" * 50)
    print("  ✓ TESTE PRODUCT REFERENCE POLICY: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
