"""Testa decomposição de briefing em cenas via OpenAI API."""

import sys
import json
import time
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from scripts.config import OPENAI_API_KEY, OPENAI_PLANNER_MODEL, OUTPUT_DIR
from scripts.openai_utils import create_text_response


SYSTEM_PROMPT = """Você é o diretor criativo da marca José Wipes. Receba um briefing de vídeo em português e decomponha em cenas. Para cada cena retorne: titulo, tipo (lip_sync/broll/product_shot), prompt em INGLÊS otimizado para IA generativa (mín 50 palavras), duracao_alvo em segundos, notas_audio em português. Responda APENAS com JSON puro, sem markdown."""

BRIEFING_TESTE = """Quero um vídeo curto de 30 segundos no estilo grupo de apoio. Um cara confessa que usou papel higiênico, o grupo reage com choque, e no final aparece o José Wipes como a salvação. Para Instagram Reels."""


def main():
    print("=" * 50)
    print("TESTE: OpenAI API — Decomposição de Briefing")
    print("=" * 50)

    # [1/4] Validar config
    print("\n[1/4] Validando configuração...")
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("your_"):
        print("  ✗ OPENAI_API_KEY não configurado no .env")
        return 1
    print("  ✓ API key encontrada")

    # [2/4] Enviar briefing
    print(f"\n[2/4] Enviando briefing para {OPENAI_PLANNER_MODEL}...")
    print(f"  Briefing: {BRIEFING_TESTE[:80]}...")

    inicio = time.time()
    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        resposta = create_text_response(
            client=client,
            model=OPENAI_PLANNER_MODEL,
            instructions=SYSTEM_PROMPT,
            user_input=BRIEFING_TESTE,
            max_output_tokens=3000,
        )
        resposta = resposta.strip()
        duracao = time.time() - inicio
        print(f"  ✓ Resposta recebida em {duracao:.1f}s")

    except Exception as e:
        print(f"  ✗ Erro ao chamar OpenAI: {e}")
        return 1

    # [3/4] Parsear JSON
    print("\n[3/4] Parseando resposta JSON...")
    try:
        texto = resposta
        if texto.startswith("```"):
            texto = texto.split("\n", 1)[1]
            if texto.endswith("```"):
                texto = texto[:-3]
            texto = texto.strip()

        resultado = json.loads(texto)
        print(f"  ✓ JSON válido!")

    except json.JSONDecodeError as e:
        print(f"  ✗ JSON inválido: {e}")
        print(f"  Resposta bruta:\n{resposta[:500]}")
        return 1

    # [4/4] Validar estrutura
    print("\n[4/4] Validando estrutura...")
    erros = 0

    cenas = resultado if isinstance(resultado, list) else resultado.get("cenas", [])

    if not cenas:
        print("  ✗ Nenhuma cena encontrada no resultado")
        erros += 1
    else:
        print(f"  ✓ {len(cenas)} cenas encontradas")

    for i, cena in enumerate(cenas):
        campos_ok = True
        for campo in ["titulo", "tipo", "prompt", "duracao_alvo"]:
            if campo not in cena:
                print(f"  ✗ Cena {i+1}: campo '{campo}' ausente")
                campos_ok = False
                erros += 1

        if campos_ok:
            prompt = cena.get("prompt", "")
            palavras_pt = sum(1 for w in ["de", "que", "para", "com", "uma", "um"] if f" {w} " in prompt.lower())
            palavras_en = sum(1 for w in ["the", "a", "in", "with", "and", "of"] if f" {w} " in prompt.lower())

            if palavras_en >= palavras_pt:
                print(f"  ✓ Cena {i+1}: '{cena['titulo']}' — prompt em inglês ({len(prompt.split())} palavras)")
            else:
                print(f"  ✗ Cena {i+1}: prompt parece estar em português")
                erros += 1

    out_path = OUTPUT_DIR / "teste_claude_decomposicao.json"
    out_path.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✓ Resultado salvo em: {out_path}")

    if erros > 0:
        print(f"\n{'=' * 50}")
        print(f"  ✗ TESTE DECOMPOSIÇÃO: FALHOU ({erros} erros)")
        return 1

    print(f"\n{'=' * 50}")
    print("  ✓ TESTE DECOMPOSIÇÃO: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
