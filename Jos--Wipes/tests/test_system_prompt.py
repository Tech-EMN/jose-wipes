"""Testa o system prompt: montagem e decomposição de 3 briefings via Claude."""

import sys
import json
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from scripts.config import OPENAI_API_KEY, OPENAI_PLANNER_MODEL
from scripts.openai_utils import create_text_response


def main():
    print("=" * 50)
    print("TESTE: System Prompt")
    print("=" * 50)

    # [1/2] Montar prompt
    print("\n[1/2] Montando system prompt...")
    try:
        from scripts.system_prompt import montar_system_prompt, info_prompt
        prompt = montar_system_prompt()
        chars = len(prompt)
        tokens = chars // 4
        print(f"  ✓ Montado: {chars} chars (~{tokens} tokens)")

        # Verificar componentes
        for marker in ["IDENTIDADE", "BRANDBOOK", "MODELOS", "SCHEMA", "GUARDRAILS"]:
            if marker in prompt:
                print(f"  ✓ {marker}")
            else:
                print(f"  ✗ {marker} ausente")

    except Exception as e:
        print(f"  ✗ Erro ao montar: {e}")
        return 1

    # [2/2] Testar briefings (requer API key)
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("your_"):
        print("\n[2/2] OPENAI_API_KEY não configurada — pulando teste de briefings")
        print(f"\n{'=' * 50}")
        print("  ✓ TESTE SYSTEM PROMPT: PASSOU (parcial — sem teste de API)")
        return 0

    print(f"\n[2/2] Testando 3 briefings via {OPENAI_PLANNER_MODEL}...")
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)

    briefings = [
        ("Completo", "Vídeo de 30s estilo grupo de apoio. João confessa que usou papel, grupo reage chocado, líder revela José Wipes. Para Instagram."),
        ("Vago", "Faz algo sobre banheiro de aeroporto"),
        ("Product Demo", "Vídeo curto de 10 segundos mostrando o produto José Wipes em close, estilo premium. Narração curta."),
    ]

    erros = 0
    for nome, briefing in briefings:
        print(f"\n  --- Briefing: {nome} ---")
        print(f"  Input: {briefing[:60]}...")

        try:
            resposta = create_text_response(
                client=client,
                model=OPENAI_PLANNER_MODEL,
                instructions=prompt,
                user_input=briefing,
                max_output_tokens=6000,
            )
            resposta = resposta.strip()
            if resposta.startswith("```"):
                resposta = resposta.split("\n", 1)[1]
                if resposta.endswith("```"):
                    resposta = resposta[:-3]
                resposta = resposta.strip()

            plano = json.loads(resposta)

            # Validar
            checks = []

            # JSON válido ✓
            checks.append(("JSON válido", True))

            # Cenas existem
            cenas = plano.get("cenas", [])
            checks.append(("Tem cenas", len(cenas) > 0))

            # Prompts em inglês
            en_words = ["the", "with", "in", "and", "of", "light"]
            all_en = all(
                any(w in c.get("prompt", "").lower() for w in en_words)
                for c in cenas
            )
            checks.append(("Prompts em inglês", all_en))

            # Card final
            has_card = "card_final" in plano
            checks.append(("Card final", has_card))

            # Duração
            dur_total = sum(c.get("duracao_segundos", 0) for c in cenas)
            if has_card:
                dur_total += plano["card_final"].get("duracao_segundos", 0)
            checks.append(("Duração > 0", dur_total > 0))

            for check_nome, ok in checks:
                icon = "✓" if ok else "✗"
                print(f"    {icon} {check_nome}")
                if not ok:
                    erros += 1

            print(f"    Cenas: {len(cenas)}, Duração: {dur_total}s")

        except json.JSONDecodeError:
            print(f"    ✗ JSON inválido na resposta")
            erros += 1
        except Exception as e:
            print(f"    ✗ Erro: {e}")
            erros += 1

    if erros > 0:
        print(f"\n{'=' * 50}")
        print(f"  ✗ TESTE SYSTEM PROMPT: FALHOU ({erros} erros)")
        return 1

    print(f"\n{'=' * 50}")
    print("  ✓ TESTE SYSTEM PROMPT: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
