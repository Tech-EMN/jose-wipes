"""Pipeline orquestrador: briefing → decomposição → geração → composição → upload."""

import sys
import json
import argparse
import time
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.config import (
    decompor_briefing,
    OUTPUT_DIR,
    ASSETS_DIR,
    obter_logo_path,
    obter_url_imagem_produto,
)
from scripts.product_reference import (
    aplicar_regra_referencia_produto_plano,
    scene_dict_pede_referencia_produto,
)
from scripts.gerador_midia import (
    gerar_video_higgsfield, gerar_audio_elevenlabs,
    combinar_video_audio, imagem_para_video_kenburns
)
from scripts.compositor import (
    compor_video_final, adicionar_texto_overlay, overlay_produto,
    gerar_card_final_com_produto, compor_produto_na_imagem
)
from scripts.uploader import upload_para_drive
from scripts.higgsfield_utils import upload_higgsfield_file


def executar_pipeline(briefing=None, plano=None):
    """Pipeline completo: briefing → vídeo final. Retorna dict de resultado."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    resultado = {
        "sucesso": False,
        "video_local": None,
        "video_drive": None,
        "plano": None,
        "duracao_total": 0,
        "cenas_geradas": [],
        "cenas_falharam": [],
    }

    print("\n" + "=" * 60)
    print("  JOSÉ WIPES PIPELINE — Geração de Vídeo")
    print("=" * 60)

    # ========== ETAPA 1: Decomposição ==========
    if plano is None and briefing:
        print(f"\n{'─' * 60}")
        print(f"  ETAPA 1: Decompondo briefing com Claude...")
        print(f"  Briefing: {briefing[:100]}...")
        print(f"{'─' * 60}")

        plano = decompor_briefing(briefing)
        if not plano:
            print("  ✗ Falha na decomposição do briefing!")
            return resultado

        # Salvar plano
        plano_path = OUTPUT_DIR / "final" / f"plano_{ts}.json"
        plano_path.write_text(json.dumps(plano, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  ✓ Plano salvo: {plano_path}")

    elif plano and isinstance(plano, (str, Path)):
        plano_path = Path(plano)
        plano = json.loads(plano_path.read_text(encoding="utf-8"))

    if not plano:
        print("  ✗ Nenhum plano fornecido!")
        return resultado

    plano = aplicar_regra_referencia_produto_plano(plano, briefing=briefing)
    resultado["plano"] = plano
    cenas = plano.get("cenas", [])
    card_final = plano.get("card_final")

    titulo = plano.get("titulo_video", "jose_wipes_video")
    print(f"\n  Título: {titulo}")
    print(f"  Cenas: {len(cenas)} + card final")
    print(f"  Duração estimada: {plano.get('duracao_total_estimada', '?')}s")

    # ========== ETAPA 2: Gerar cada cena ==========
    cenas_prontas = []

    for i, cena in enumerate(cenas, 1):
        numero = cena.get("numero", i)
        titulo_cena = cena.get("titulo", f"Cena {numero}")
        tipo = cena.get("tipo", "broll")
        modelo = cena.get("modelo", "kling-video/v2.1/master/text-to-video")
        prompt = cena.get("prompt", "")
        duracao = cena.get("duracao_segundos", 6)
        aspecto = cena.get("aspecto", "9:16")
        resolucao = cena.get("resolucao", "1080p")

        print(f"\n{'─' * 60}")
        print(f"  CENA {numero}/{len(cenas)}: {titulo_cena}")
        print(f"  Tipo: {tipo} | Modelo: {modelo} | Duração: {duracao}s")
        print(f"{'─' * 60}")

        cena_base = OUTPUT_DIR / "cenas" / f"cena_{numero:02d}_{ts}"

        try:
            ref_url = None
            if scene_dict_pede_referencia_produto(cena):
                try:
                    ref_url = obter_url_imagem_produto()
                    print(f"  Referência visual do produto injetada")
                except Exception as e:
                    print(f"  Não foi possível carregar referência do produto: {e}")

            # A) Gerar vídeo/imagem
            is_image = "seedream" in modelo or "text-to-image" in modelo or "soul" in modelo or "reve" in modelo
            is_image_to_video = tipo == "image_to_video"

            if is_image_to_video:
                # Gerar imagem primeiro, depois animar com modelo de vídeo
                modelo_imagem = cena.get("modelo_imagem", "higgsfield-ai/soul/standard")
                print(f"  Etapa 1: Gerando imagem com {modelo_imagem}...")
                img_path = gerar_video_higgsfield(
                    modelo_imagem, prompt, aspecto, resolucao, duracao,
                    output_path=f"{cena_base}.png",
                    reference_image_url=ref_url
                )
                if not img_path:
                    raise Exception("Falha na geração de imagem para image_to_video")

                # Compor produto real na imagem se produto_overlay ativo
                produto_config = cena.get("produto_overlay", {})
                if produto_config.get("ativo", False):
                    prod_pos = produto_config.get("posicao", "mao_direita")
                    prod_tam = produto_config.get("tamanho_pct", 30)
                    img_composta = compor_produto_na_imagem(
                        img_path, f"{cena_base}_composta.png",
                        posicao=prod_pos, tamanho_pct=prod_tam
                    )
                    if img_composta:
                        img_path = img_composta
                        print(f"  Produto real composto na imagem")

                # Upload da imagem para animar
                img_url = upload_higgsfield_file(img_path)
                print(f"  Etapa 2: Animando com {modelo}...")
                video_path = gerar_video_higgsfield(
                    modelo, prompt, aspecto, resolucao, duracao,
                    output_path=f"{cena_base}.mp4",
                    reference_image_url=img_url
                )
                if not video_path:
                    # Fallback: Ken Burns se animação falhar
                    print(f"  Animação falhou, usando Ken Burns como fallback...")
                    video_path = imagem_para_video_kenburns(
                        img_path, duracao, f"{cena_base}_kb.mp4"
                    )
                    if not video_path:
                        raise Exception("Falha no fallback Ken Burns")

            elif is_image:
                # Gerar imagem → Ken Burns
                img_path = gerar_video_higgsfield(
                    modelo, prompt, aspecto, resolucao, duracao,
                    output_path=f"{cena_base}.png",
                    reference_image_url=ref_url
                )
                if not img_path:
                    raise Exception("Falha na geração de imagem")

                video_path = imagem_para_video_kenburns(
                    img_path, duracao, f"{cena_base}_kb.mp4"
                )
                if not video_path:
                    raise Exception("Falha no Ken Burns")
            else:
                # Gerar vídeo direto
                video_path = gerar_video_higgsfield(
                    modelo, prompt, aspecto, resolucao, duracao,
                    output_path=f"{cena_base}.mp4",
                    reference_image_url=ref_url
                )
                if not video_path:
                    raise Exception("Falha na geração de vídeo")

            # B) Áudio
            audio_config = cena.get("audio", {})
            audio_tipo = audio_config.get("tipo", "nenhum")

            if audio_tipo == "overlay":
                persona = audio_config.get("persona_voz", "narrador")
                texto_fala = audio_config.get("texto_fala", "")
                if texto_fala and persona:
                    audio_path = gerar_audio_elevenlabs(
                        persona, texto_fala, f"{cena_base}_audio.mp3"
                    )
                    if audio_path:
                        combined = combinar_video_audio(
                            video_path, audio_path, f"{cena_base}_combined.mp4"
                        )
                        if combined:
                            video_path = combined

            # C) Overlay do produto real (imagem da embalagem)
            # Só aplica overlay no vídeo para cenas que NÃO são image_to_video
            # (em image_to_video o produto já foi composto na imagem antes de animar)
            produto_config = cena.get("produto_overlay", {})
            if produto_config.get("ativo", False) and not is_image_to_video:
                prod_posicao = produto_config.get("posicao", "centro")
                prod_tamanho = produto_config.get("tamanho_pct", 55)
                prod_inicio = produto_config.get("inicio_seg", None)
                prod_result = overlay_produto(
                    video_path, f"{cena_base}_prod.mp4",
                    posicao=prod_posicao, tamanho_pct=prod_tamanho,
                    inicio_seg=prod_inicio
                )
                if prod_result:
                    video_path = prod_result

            # D) Texto overlay
            texto_config = cena.get("texto_overlay", {})
            texto = texto_config.get("texto")
            if texto:
                posicao = texto_config.get("posicao", "centro_inferior")
                text_result = adicionar_texto_overlay(
                    video_path, texto, f"{cena_base}_text.mp4", posicao
                )
                if text_result:
                    video_path = text_result

            cenas_prontas.append(str(video_path))
            resultado["cenas_geradas"].append(titulo_cena)
            print(f"  ✓ Cena {numero} pronta!")

        except Exception as e:
            print(f"  ✗ Cena {numero} falhou: {e}")
            resultado["cenas_falharam"].append(titulo_cena)
            continue

    # ========== ETAPA 3: Card Final ==========
    if card_final:
        print(f"\n{'─' * 60}")
        print(f"  CARD FINAL")
        print(f"{'─' * 60}")

        try:
            cf_duracao = card_final.get("duracao_segundos", 4)
            cf_base = OUTPUT_DIR / "cenas" / f"card_final_{ts}"

            # Card final usa imagem REAL do produto (não IA)
            print(f"  Usando imagem real do produto para card final")
            video = gerar_card_final_com_produto(f"{cf_base}_produto.mp4", duracao=cf_duracao)

            if video:
                # Áudio overlay
                cf_audio = card_final.get("audio", {})
                if cf_audio.get("tipo") == "overlay":
                    persona = cf_audio.get("persona_voz", "narrador")
                    texto = cf_audio.get("texto_fala", "José Wipes. A recuperação que você merece.")
                    audio = gerar_audio_elevenlabs(persona, texto, f"{cf_base}_audio.mp3")
                    if audio:
                        combined = combinar_video_audio(video, audio, f"{cf_base}_combined.mp4")
                        if combined:
                            video = combined

                # Texto overlay
                cf_texto = card_final.get("texto_overlay", {})
                linhas = []
                if cf_texto.get("linha1"):
                    linhas.append(cf_texto["linha1"])
                if cf_texto.get("linha2"):
                    linhas.append(cf_texto["linha2"])
                if linhas:
                    texto_completo = " | ".join(linhas)
                    text_result = adicionar_texto_overlay(
                        video, texto_completo, f"{cf_base}_text.mp4", "centro_inferior"
                    )
                    if text_result:
                        video = text_result

                cenas_prontas.append(str(video))
                print(f"  ✓ Card final pronto!")
            else:
                print(f"  ✗ Card final falhou")

        except Exception as e:
            print(f"  ✗ Card final falhou: {e}")

    # ========== ETAPA 4: Composição Final ==========
    if not cenas_prontas:
        print(f"\n  ✗ Nenhuma cena gerada! Pipeline falhou.")
        return resultado

    print(f"\n{'─' * 60}")
    print(f"  COMPOSIÇÃO FINAL ({len(cenas_prontas)} cenas)")
    print(f"{'─' * 60}")

    logo_path = obter_logo_path()
    video_final = compor_video_final(cenas_prontas, titulo, logo_path)

    if video_final:
        resultado["video_local"] = str(video_final)
        resultado["sucesso"] = True

        # ========== ETAPA 5: Upload ==========
        print(f"\n{'─' * 60}")
        print(f"  UPLOAD GOOGLE DRIVE")
        print(f"{'─' * 60}")

        drive_result = upload_para_drive(video_final)
        if drive_result:
            resultado["video_drive"] = drive_result

    # ========== RESUMO ==========
    print(f"\n{'=' * 60}")
    print(f"  RESUMO DO PIPELINE")
    print(f"{'=' * 60}")
    print(f"  Sucesso: {'✓' if resultado['sucesso'] else '✗'}")
    print(f"  Cenas geradas: {len(resultado['cenas_geradas'])}/{len(cenas)}")
    if resultado["cenas_falharam"]:
        print(f"  Cenas falharam: {resultado['cenas_falharam']}")
    if resultado["video_local"]:
        print(f"  Vídeo local: {resultado['video_local']}")
    if resultado["video_drive"]:
        print(f"  Google Drive: {resultado['video_drive'].get('link', '?')}")
    print(f"{'=' * 60}\n")

    return resultado


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline José Wipes — Briefing → Vídeo",
        usage='python scripts/pipeline.py "Faz um vídeo de 30s no estilo grupo de apoio"'
    )
    parser.add_argument("briefing", nargs="?", help="Briefing em texto")
    parser.add_argument("--arquivo", type=str, help="Ler briefing de arquivo")
    parser.add_argument("--plano", type=str, help="Usar plano JSON pré-gerado")
    args = parser.parse_args()

    if args.plano:
        executar_pipeline(plano=args.plano)
    elif args.arquivo:
        briefing = Path(args.arquivo).read_text(encoding="utf-8")
        executar_pipeline(briefing=briefing)
    elif args.briefing:
        executar_pipeline(briefing=args.briefing)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
