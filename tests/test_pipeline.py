"""Valida estrutura do pipeline: módulos, funções, dependências, configs."""

import sys
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))


def main():
    print("=" * 50)
    print("TESTE: Pipeline — Validação Estrutural")
    print("=" * 50)

    erros = 0

    # [1/5] Módulos importam
    print("\n[1/5] Verificando módulos...")
    modulos = {
        "jose_wipes.config": None,
        "jose_wipes.composition.product_reference": None,
        "jose_wipes.planning.system_prompt": None,
        "jose_wipes.integrations.gerador_midia": None,
        "jose_wipes.composition.compositor": None,
        "jose_wipes.integrations.uploader": None,
        "scripts.pipeline": None,
        "scripts.web_server": None,
    }

    for mod_name in modulos:
        try:
            modulos[mod_name] = __import__(mod_name, fromlist=[""])
            print(f"  ✓ {mod_name}")
        except Exception as e:
            print(f"  ✗ {mod_name}: {e}")
            erros += 1

    # [2/5] Funções essenciais
    print("\n[2/5] Verificando funções essenciais...")
    funcoes = [
        ("jose_wipes.config", "validar_configuracao"),
        ("jose_wipes.config", "carregar_brandbook"),
        ("jose_wipes.config", "brandbook_para_contexto"),
        ("jose_wipes.config", "carregar_vozes"),
        ("jose_wipes.config", "gerar_audio"),
        ("jose_wipes.config", "decompor_briefing"),
        ("jose_wipes.composition.product_reference", "obter_imagem_produto_path"),
        ("jose_wipes.composition.product_reference", "prompt_pede_referencia_produto"),
        ("jose_wipes.planning.system_prompt", "montar_system_prompt"),
        ("jose_wipes.integrations.gerador_midia", "gerar_video_higgsfield"),
        ("jose_wipes.integrations.gerador_midia", "combinar_video_audio"),
        ("jose_wipes.integrations.gerador_midia", "imagem_para_video_kenburns"),
        ("jose_wipes.composition.compositor", "compor_video_final"),
        ("jose_wipes.integrations.uploader", "upload_para_drive"),
        ("scripts.pipeline", "run_pipeline"),
        ("scripts.web_server", "start_web_server"),
        ("scripts.web_server", "stop_web_server"),
    ]

    for mod_name, func_name in funcoes:
        mod = modulos.get(mod_name)
        if mod and hasattr(mod, func_name) and callable(getattr(mod, func_name)):
            print(f"  ✓ {mod_name}.{func_name}()")
        else:
            print(f"  ✗ {mod_name}.{func_name}() — não encontrada")
            erros += 1

    # [3/5] FFmpeg e ffprobe
    print("\n[3/5] Verificando FFmpeg...")
    import subprocess
    for cmd in ["ffmpeg", "ffprobe"]:
        try:
            result = subprocess.run([cmd, "-version"], capture_output=True, text=True, timeout=10)
            print(f"  ✓ {cmd}")
        except FileNotFoundError:
            print(f"  ✗ {cmd} não encontrado")
            erros += 1

    # [4/5] Configs existem
    print("\n[4/5] Verificando configs...")
    from jose_wipes.config import CONFIG_DIR, PROJECT_ROOT
    configs = [
        (CONFIG_DIR / "brandbook.json", True),
        (CONFIG_DIR / "prompts_library.json", True),
        (PROJECT_ROOT / ".env", True),
        (CONFIG_DIR / "vozes.json", False),  # Opcional
    ]

    for path, obrigatorio in configs:
        if path.exists():
            print(f"  ✓ {path.name}")
        elif obrigatorio:
            print(f"  ✗ {path.name} — não encontrado")
            erros += 1
        else:
            print(f"  ! {path.name} — opcional, não encontrado")

    # [5/5] Resumo
    total_checks = len(modulos) + len(funcoes) + 2 + len(configs)
    passou = total_checks - erros

    if erros > 0:
        print(f"\n{'=' * 50}")
        print(f"  ✗ TESTE PIPELINE: FALHOU ({erros} erros, {passou}/{total_checks} OK)")
        return 1

    print(f"\n{'=' * 50}")
    print(f"  ✓ TESTE PIPELINE: PASSOU ({passou}/{total_checks})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
