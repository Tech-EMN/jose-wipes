"""Gerencia teste e avaliação de prompts da biblioteca José Wipes."""

import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.config import CONFIG_DIR, OUTPUT_DIR, HF_API_KEY, HF_API_SECRET


PROMPTS_FILE = CONFIG_DIR / "prompts_library.json"


def carregar_prompts():
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar_prompts(data):
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def todos_os_prompts(data):
    """Retorna lista flat de todos os prompts (vídeo + imagem)."""
    prompts = []
    for categoria, itens in data.get("video", {}).items():
        for p in itens:
            p["_categoria"] = f"video/{categoria}"
            prompts.append(p)
    for p in data.get("imagem", []):
        p["_categoria"] = "imagem"
        prompts.append(p)
    return prompts


def encontrar_prompt(data, prompt_id):
    """Encontra prompt por ID e retorna (prompt, categoria_path)."""
    for cat, itens in data.get("video", {}).items():
        for p in itens:
            if p["id"] == prompt_id:
                return p, f"video.{cat}"
    for p in data.get("imagem", []):
        if p["id"] == prompt_id:
            return p, "imagem"
    return None, None


def mostrar_status(data):
    """Mostra tabela com todos os prompts e status."""
    prompts = todos_os_prompts(data)

    print(f"\n{'ID':<15} {'Nome':<25} {'Score':<7} {'Status':<10} {'Categoria'}")
    print("-" * 80)

    for p in prompts:
        score = p.get("score", 0)
        if score == 0:
            status = "pendente"
            icon = "[ ]"
        elif score >= 3:
            status = "aprovado"
            icon = "[+]"
        else:
            status = "reprovado"
            icon = "[-]"

        print(f"  {icon} {p['id']:<12} {p['nome']:<25} {score:<7} {status:<10} {p.get('_categoria', '')}")

    testados = sum(1 for p in prompts if p.get("score", 0) > 0)
    aprovados = sum(1 for p in prompts if p.get("score", 0) >= 3)
    print(f"\nTotal: {len(prompts)} | Testados: {testados} | Aprovados: {aprovados}")


def testar_prompt(data, prompt_id):
    """Testa um prompt específico na Higgsfield."""
    prompt_data, cat_path = encontrar_prompt(data, prompt_id)
    if not prompt_data:
        print(f"  Prompt '{prompt_id}' não encontrado!")
        return False

    print(f"\n{'=' * 50}")
    print(f"Testando: {prompt_data['id']} — {prompt_data['nome']}")
    print(f"Modelo: {prompt_data['modelo_recomendado']}")
    print(f"Prompt: {prompt_data['prompt'][:100]}...")
    print(f"{'=' * 50}")

    if not HF_API_KEY or HF_API_KEY.startswith("your_"):
        print("  HF_API_KEY não configurado!")
        return False

    import higgsfield_client

    modelo = prompt_data["modelo_recomendado"]
    params = dict(prompt_data.get("parametros", {}))
    params["prompt"] = prompt_data["prompt"]

    inicio = time.time()
    try:
        controller = higgsfield_client.submit(
            model=modelo,
            arguments=params,
            api_key=HF_API_KEY,
            api_secret=HF_API_SECRET,
        )

        print("  Aguardando geração...")
        while True:
            status = controller.poll_request_status()
            state = status.get("status", status.get("state", "unknown"))
            print(f"    Status: {state}")

            if state in ("Completed", "completed", "succeeded"):
                break
            elif state in ("Failed", "failed", "error", "NSFW", "nsfw"):
                print(f"    Falhou: {status}")
                return False
            time.sleep(8)

        duracao = time.time() - inicio
        print(f"  Gerado em {duracao:.1f}s")

        # Extrair e baixar
        url = None
        for getter in [
            lambda r: r.get("result", {}).get("images", [{}])[0].get("url"),
            lambda r: r.get("result", {}).get("videos", [{}])[0].get("url"),
            lambda r: r.get("result", {}).get("url"),
            lambda r: r.get("url"),
        ]:
            try:
                url = getter(status)
                if url:
                    break
            except (IndexError, KeyError, TypeError):
                continue

        if url:
            ext = ".png" if "seedream" in modelo or "text-to-image" in modelo else ".mp4"
            out_path = OUTPUT_DIR / f"teste_{prompt_id}{ext}"
            subprocess.run(["curl", "-sL", "-o", str(out_path), url], timeout=120)
            print(f"  Salvo: {out_path}")

        # Pedir score
        print(f"\n  Avalie este resultado (0-5):")
        print(f"  0=não testado, 1=péssimo, 2=ruim, 3=aceitável, 4=bom, 5=excelente")
        try:
            score = int(input("  Score: ").strip())
            notas = input("  Notas: ").strip()
        except (ValueError, EOFError):
            score = 0
            notas = "input cancelado"

        # Atualizar
        prompt_data["score"] = score
        prompt_data["score_notas"] = notas
        prompt_data["testado_em"] = datetime.now().isoformat()

        salvar_prompts(data)
        print(f"  ✓ Prompt {prompt_id} atualizado: score={score}")
        return True

    except Exception as e:
        print(f"  Erro: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Gerenciador de teste de prompts José Wipes")
    parser.add_argument("--status", action="store_true", help="Mostra status de todos os prompts")
    parser.add_argument("--id", type=str, help="Testa prompt específico por ID")
    parser.add_argument("--categoria", choices=["video", "imagem"], help="Testa todos pendentes de uma categoria")
    parser.add_argument("--pendentes", action="store_true", help="Testa todos com score=0")
    args = parser.parse_args()

    data = carregar_prompts()

    if args.status or (not args.id and not args.categoria and not args.pendentes):
        mostrar_status(data)
        return

    if args.id:
        testar_prompt(data, args.id)
        return

    prompts = todos_os_prompts(data)

    if args.categoria:
        pendentes = [p for p in prompts if p.get("score", 0) == 0 and p.get("_categoria", "").startswith(args.categoria)]
    elif args.pendentes:
        pendentes = [p for p in prompts if p.get("score", 0) == 0]
    else:
        pendentes = []

    if not pendentes:
        print("  Nenhum prompt pendente!")
        return

    print(f"\n{len(pendentes)} prompts pendentes para testar:")
    for p in pendentes:
        testar_prompt(data, p["id"])

    mostrar_status(data)


if __name__ == "__main__":
    main()
