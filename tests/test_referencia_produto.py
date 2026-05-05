"""Valida a integração da imagem de referência do produto no pipeline."""

import sys
import json
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from scripts.config import ASSETS_DIR, CONFIG_DIR, HF_API_KEY, HF_API_SECRET, PRODUCT_IMAGE_PATH
from scripts.product_reference import obter_imagem_produto_path


def main():
    print("=" * 50)
    print("TESTE: Referência Visual do Produto")
    print("=" * 50)

    erros = 0

    # [1/5] Imagem existe
    print("\n[1/5] Verificando imagem do produto...")
    resolved_path = obter_imagem_produto_path()
    if resolved_path.exists():
        print(f"  ✓ Imagem encontrada: {resolved_path}")
    else:
        print(f"  ✗ Imagem NÃO encontrada: {resolved_path}")
        erros += 1

    if PRODUCT_IMAGE_PATH != resolved_path:
        print(f"  ✗ PRODUCT_IMAGE_PATH está divergente do resolver: {PRODUCT_IMAGE_PATH}")
        erros += 1

    # [2/5] Tamanho > 100KB
    print("\n[2/5] Verificando tamanho da imagem...")
    if resolved_path.exists():
        size_kb = resolved_path.stat().st_size / 1024
        if size_kb > 100:
            print(f"  ✓ Tamanho: {size_kb:.0f} KB (> 100KB)")
        else:
            print(f"  ✗ Tamanho muito pequeno: {size_kb:.0f} KB (esperado > 100KB)")
            erros += 1
    else:
        print(f"  ✗ Imagem não existe, não é possível verificar tamanho")
        erros += 1

    # [3/5] Upload via Higgsfield
    print("\n[3/5] Testando upload via higgsfield_client...")
    if not HF_API_KEY or HF_API_KEY.startswith("your_"):
        print(f"  ! HF_API_KEY não configurada — pulando teste de upload")
    else:
        try:
            import higgsfield_client
            url = higgsfield_client.upload_file(str(resolved_path))
            if url and url.startswith("http"):
                print(f"  ✓ Upload OK! URL: {url[:80]}...")
            else:
                print(f"  ✗ Upload retornou valor inesperado: {url}")
                erros += 1
        except Exception as e:
            msg = str(e)
            if "10061" in msg or "Connection" in msg or "conexão" in msg.lower():
                print(f"  ! Upload indisponível no ambiente atual — pulando: {e}")
            else:
                print(f"  ✗ Erro no upload: {e}")
                erros += 1

    # [4/5] Brandbook tem foto_referencia_disponivel
    print("\n[4/5] Verificando brandbook...")
    try:
        with open(CONFIG_DIR / "brandbook.json", "r", encoding="utf-8") as f:
            bb = json.load(f)

        produto = bb.get("produto", {})
        if produto.get("foto_referencia_disponivel") is True:
            print(f"  ✓ foto_referencia_disponivel = true")
        else:
            print(f"  ✗ foto_referencia_disponivel não é true")
            erros += 1

        if produto.get("foto_referencia_path"):
            print(f"  ✓ foto_referencia_path: {produto['foto_referencia_path']}")
        else:
            print(f"  ✗ foto_referencia_path ausente")
            erros += 1

        comp = bb.get("composicao_final", {})
        if comp.get("produto_referencia", {}).get("usar_sempre") is True:
            print(f"  ✓ composicao_final.produto_referencia.usar_sempre = true")
        else:
            print(f"  ✗ composicao_final.produto_referencia.usar_sempre não é true")
            erros += 1

    except Exception as e:
        print(f"  ✗ Erro ao ler brandbook: {e}")
        erros += 1

    # [5/5] Prompts de produto têm usar_imagem_produto
    print("\n[5/5] Verificando prompts de produto...")
    try:
        with open(CONFIG_DIR / "prompts_library.json", "r", encoding="utf-8") as f:
            pl = json.load(f)

        ids_produto = [
            "vid_ga_04", "vid_ga_05", "vid_prod_01", "vid_prod_02",
            "vid_prod_03", "vid_trans_01", "img_01", "img_02"
        ]

        # Coletar todos os prompts
        todos = []
        for cat, itens in pl.get("video", {}).items():
            todos.extend(itens)
        todos.extend(pl.get("imagem", []))

        for pid in ids_produto:
            prompt_data = next((p for p in todos if p["id"] == pid), None)
            if prompt_data is None:
                print(f"  ✗ {pid}: não encontrado")
                erros += 1
                continue

            if prompt_data.get("usar_imagem_produto") is True:
                print(f"  ✓ {pid}: usar_imagem_produto = true")
            else:
                print(f"  ✗ {pid}: usar_imagem_produto não é true")
                erros += 1

    except Exception as e:
        print(f"  ✗ Erro ao ler prompts_library: {e}")
        erros += 1

    # Resultado
    if erros > 0:
        print(f"\n{'=' * 50}")
        print(f"  ✗ TESTE REFERÊNCIA PRODUTO: FALHOU ({erros} erros)")
        return 1

    print(f"\n{'=' * 50}")
    print("  ✓ TESTE REFERÊNCIA PRODUTO: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
