"""Testa geração de imagem na Higgsfield Cloud API."""

import sys
import time
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from scripts.config import HF_API_KEY, HF_API_SECRET, OUTPUT_DIR


def main():
    print("=" * 50)
    print("TESTE: Higgsfield — Geração de Imagem")
    print("=" * 50)

    # [1/4] Validar config
    print("\n[1/4] Validando configuração...")
    if not HF_API_KEY or HF_API_KEY.startswith("your_"):
        print("  ✗ HF_API_KEY não configurado no .env")
        return 1
    if not HF_API_SECRET or HF_API_SECRET.startswith("your_"):
        print("  ✗ HF_API_SECRET não configurado no .env")
        return 1
    print("  ✓ API keys encontradas")

    # [2/4] Importar client
    print("\n[2/4] Importando higgsfield_client...")
    try:
        import higgsfield_client
        print("  ✓ higgsfield_client importado")
    except ImportError:
        print("  ✗ higgsfield_client não instalado. Rode: pip install higgsfield-client")
        return 1

    # [3/4] Gerar imagem
    print("\n[3/4] Gerando imagem...")
    prompt = (
        "Professional product photography of a white wet wipes package for men, "
        "bold black typography, minimal design, dark wood surface, dramatic side "
        "lighting, premium masculine aesthetic, studio shot"
    )
    print(f"  Prompt: {prompt[:80]}...")

    inicio = time.time()
    try:
        controller = higgsfield_client.submit(
            model="bytedance/seedream/v4/text-to-image",
            arguments={
                "prompt": prompt,
                "resolution": "2K",
                "aspect_ratio": "9:16",
            },
            api_key=HF_API_KEY,
            api_secret=HF_API_SECRET,
        )

        print("  Aguardando geração...")
        while True:
            status = controller.poll_request_status()
            state = status.get("status", status.get("state", "unknown"))
            print(f"    Status: {state}")

            if state in ("Completed", "completed", "COMPLETED", "succeeded"):
                break
            elif state in ("Failed", "failed", "FAILED", "error"):
                print(f"  ✗ Geração falhou: {status}")
                return 1
            elif state in ("NSFW", "nsfw"):
                print(f"  ✗ Conteúdo marcado como NSFW")
                return 1

            time.sleep(5)

        duracao = time.time() - inicio
        result = status

        # Extrair URL — tentar várias estruturas
        url = None
        for key_path in [
            lambda r: r.get("result", {}).get("images", [{}])[0].get("url"),
            lambda r: r.get("result", {}).get("url"),
            lambda r: r.get("images", [{}])[0].get("url"),
            lambda r: r.get("url"),
            lambda r: r.get("output", {}).get("url"),
            lambda r: r.get("result", {}).get("output", {}).get("url"),
        ]:
            try:
                url = key_path(result)
                if url:
                    break
            except (IndexError, KeyError, TypeError):
                continue

        if not url:
            print(f"  ✗ Não consegui extrair URL do resultado: {result}")
            return 1

        # [4/4] Salvar
        print(f"\n[4/4] Salvando resultado...")
        out_file = OUTPUT_DIR / "teste_higgsfield_image_url.txt"
        out_file.write_text(url, encoding="utf-8")
        print(f"  ✓ URL salva em: {out_file}")
        print(f"  ✓ URL: {url}")
        print(f"  ✓ Tempo: {duracao:.1f}s")

    except Exception as e:
        print(f"  ✗ Erro: {e}")
        print(f"  Causa provável: verifique API Key/Secret e saldo na Higgsfield")
        return 1

    print("\n" + "=" * 50)
    print("  ✓ TESTE HIGGSFIELD IMAGE: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
