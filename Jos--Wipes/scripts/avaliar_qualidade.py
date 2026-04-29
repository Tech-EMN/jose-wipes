"""Bateria de QA: roda briefings representativos e coleta avaliação humana."""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.config import CONFIG_DIR, OUTPUT_DIR
from scripts.pipeline import executar_pipeline


AVALIACOES_FILE = CONFIG_DIR / "avaliacoes_qualidade.json"

BRIEFINGS = {
    "qa_01": {
        "nome": "Grupo de Apoio Curto",
        "briefing": "Vídeo de 30 segundos estilo grupo de apoio. Confissão do João, reação de choque do grupo, revelação do produto pelo Líder. Para Instagram Reels.",
        "criterios_especificos": [
            "Expressões faciais dos personagens",
            "Iluminação dramática da sala",
            "Timing do reveal do produto",
        ]
    },
    "qa_02": {
        "nome": "Product Demo Premium",
        "briefing": "Vídeo de 15 segundos mostrando o produto José Wipes em close, estilo premium com iluminação dramática. Narração curta do narrador institucional. Para Instagram.",
        "criterios_especificos": [
            "Qualidade do close no produto",
            "Iluminação premium",
            "Narração adequada",
        ]
    },
    "qa_03": {
        "nome": "Briefing Vago",
        "briefing": "Faz algo sobre banheiro de aeroporto",
        "criterios_especificos": [
            "Interpretação criativa do briefing",
            "Coerência do roteiro gerado",
            "Defaults inteligentes aplicados",
        ]
    },
    "qa_04": {
        "nome": "Documentário Estrada",
        "briefing": "Vídeo de 20 segundos estilo documentário. Um caminhoneiro descobre José Wipes durante uma parada na estrada. Narração dramática estilo Werner Herzog. Para TikTok.",
        "criterios_especificos": [
            "Atmosfera documental",
            "Qualidade da narração dramática",
            "Cenário de estrada convincente",
            "Tom humorístico sutil",
        ]
    },
}

CRITERIOS_GERAIS = [
    "Qualidade visual",
    "Coerência narrativa",
    "Alinhamento com marca",
    "Qualidade do áudio",
    "Transições entre cenas",
    "Card final",
    "Victor aprovaria?",
]


def carregar_avaliacoes():
    if AVALIACOES_FILE.exists():
        with open(AVALIACOES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_avaliacoes(data):
    with open(AVALIACOES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def avaliar(qa_id):
    """Roda um briefing e coleta avaliação."""
    if qa_id not in BRIEFINGS:
        print(f"  ID '{qa_id}' não encontrado. Disponíveis: {list(BRIEFINGS.keys())}")
        return

    qa = BRIEFINGS[qa_id]
    print(f"\n{'=' * 60}")
    print(f"  QA: {qa_id} — {qa['nome']}")
    print(f"{'=' * 60}")

    # Executar pipeline
    resultado = executar_pipeline(briefing=qa["briefing"])

    if not resultado.get("sucesso"):
        print(f"\n  ✗ Pipeline falhou para {qa_id}")
        avaliacoes = carregar_avaliacoes()
        avaliacoes[qa_id] = {
            "nome": qa["nome"],
            "status": "falhou",
            "data": datetime.now().isoformat(),
        }
        salvar_avaliacoes(avaliacoes)
        return

    # Coletar scores
    print(f"\n{'─' * 60}")
    print(f"  AVALIAÇÃO: {qa['nome']}")
    print(f"{'─' * 60}")

    scores = {}

    print("\n  Critérios gerais (1-5):")
    for criterio in CRITERIOS_GERAIS:
        try:
            score = int(input(f"    {criterio}: ").strip())
            scores[criterio] = max(1, min(5, score))
        except (ValueError, EOFError):
            scores[criterio] = 0

    print("\n  Critérios específicos (1-5):")
    for criterio in qa.get("criterios_especificos", []):
        try:
            score = int(input(f"    {criterio}: ").strip())
            scores[criterio] = max(1, min(5, score))
        except (ValueError, EOFError):
            scores[criterio] = 0

    try:
        notas = input("\n  Notas gerais: ").strip()
    except EOFError:
        notas = ""

    # Calcular média
    valores = [v for v in scores.values() if v > 0]
    media = sum(valores) / len(valores) if valores else 0

    # Salvar
    avaliacoes = carregar_avaliacoes()
    avaliacoes[qa_id] = {
        "nome": qa["nome"],
        "status": "avaliado",
        "data": datetime.now().isoformat(),
        "scores": scores,
        "media": round(media, 2),
        "notas": notas,
        "video_local": resultado.get("video_local"),
        "video_drive": resultado.get("video_drive"),
    }
    salvar_avaliacoes(avaliacoes)
    print(f"\n  ✓ Avaliação salva! Média: {media:.1f}/5.0")


def relatorio():
    """Mostra resumo de todas as avaliações."""
    avaliacoes = carregar_avaliacoes()

    print(f"\n{'=' * 60}")
    print(f"  RELATÓRIO DE QUALIDADE — José Wipes Pipeline")
    print(f"{'=' * 60}")

    if not avaliacoes:
        print("\n  Nenhuma avaliação realizada.")
        print("  Rode: python scripts/avaliar_qualidade.py --id qa_02")
        return

    print(f"\n{'ID':<10} {'Nome':<30} {'Média':<8} {'Status':<12} {'Data'}")
    print("-" * 80)

    medias = []
    for qa_id, av in avaliacoes.items():
        media = av.get("media", 0)
        status = av.get("status", "?")
        data = av.get("data", "?")[:10]

        if media >= 4:
            icon = "[+]"
        elif media >= 3:
            icon = "[~]"
        elif media > 0:
            icon = "[-]"
        else:
            icon = "[ ]"

        print(f"  {icon} {qa_id:<8} {av.get('nome', '?'):<30} {media:<8.1f} {status:<12} {data}")

        if media > 0:
            medias.append(media)

    if medias:
        media_geral = sum(medias) / len(medias)
        print(f"\n  Média geral: {media_geral:.1f}/5.0")
        print(f"  Avaliados: {len(medias)}/{len(BRIEFINGS)}")


def main():
    parser = argparse.ArgumentParser(description="QA José Wipes Pipeline")
    parser.add_argument("--relatorio", action="store_true", help="Mostra relatório")
    parser.add_argument("--id", type=str, help="Roda avaliação específica")
    args = parser.parse_args()

    if args.relatorio:
        relatorio()
    elif args.id:
        avaliar(args.id)
    else:
        # Rodar pendentes
        avaliacoes = carregar_avaliacoes()
        pendentes = [k for k in BRIEFINGS if k not in avaliacoes or avaliacoes[k].get("status") != "avaliado"]
        if pendentes:
            print(f"\n  {len(pendentes)} briefings pendentes: {pendentes}")
            for qa_id in pendentes:
                avaliar(qa_id)
        else:
            relatorio()


if __name__ == "__main__":
    main()
