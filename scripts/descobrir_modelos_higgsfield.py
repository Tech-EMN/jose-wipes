"""Diagnostico: inspeciona higgsfield_client e proba IDs de modelo da conta."""

from __future__ import annotations

import os
import sys

CANDIDATOS = [
    "kling/3.0",
    "kling/2.1",
    "kling/2.0",
    "kling/1.6",
    "kling-video/v3.0/master/text-to-video",
    "kling-video/v2.1/master/text-to-video",
    "kling-video/v2.1/standard/text-to-video",
    "kling-video/v1.6/master/text-to-video",
    "kling-video/v1.6/standard/text-to-video",
    "bytedance/seedance/pro",
    "bytedance/seedance/v1/pro/text-to-video",
    "bytedance/seedance/v1/lite/text-to-video",
    "seedance/pro",
    "seedance/lite",
    "google/veo/3.1",
    "google/veo/v3.1/text-to-video",
    "google/veo/3.0",
    "google/veo/v3.0/text-to-video",
    "wan/2.1",
    "wan/text-to-video",
    "hailuo/video-01",
    "minimax/video-01",
    "cogvideox-5b/text-to-video",
    "ltx-video/text-to-video",
    "luma/ray",
    "luma/dream-machine",
]

ARGS_TESTE = {"prompt": "A man walking.", "aspect_ratio": "9:16", "duration": 5}


def main() -> None:
    # --- Verifica importação ---
    try:
        import higgsfield_client
    except ImportError as e:
        print(f"ERRO FATAL: higgsfield_client não instalado: {e}")
        sys.exit(1)

    # --- Inspeciona o módulo ---
    print("=== higgsfield_client ===")
    print(f"Localização: {getattr(higgsfield_client, '__file__', 'desconhecida')}")
    print(f"Versão:      {getattr(higgsfield_client, '__version__', 'desconhecida')}")
    metodos = [m for m in dir(higgsfield_client) if not m.startswith("_")]
    print(f"API pública: {', '.join(metodos)}")
    print()

    # --- Tenta listar modelos via API do client (se existir) ---
    for fn_name in ("list_applications", "list_models", "get_models", "applications"):
        fn = getattr(higgsfield_client, fn_name, None)
        if callable(fn):
            print(f"=== {fn_name}() encontrado! Chamando... ===")
            try:
                resultado = fn()
                print(resultado)
            except Exception as exc:
                print(f"  Erro: {exc}")
            print()

    # --- Verifica credenciais configuradas ---
    print("=== Credenciais ===")
    for var in ("HF_API_KEY", "HF_API_SECRET", "HIGGSFIELD_API_KEY", "HIGGSFIELD_API_SECRET"):
        val = os.getenv(var, "")
        if val:
            print(f"  {var}: configurada ({len(val)} chars)")
        else:
            print(f"  {var}: NÃO CONFIGURADA")
    print()

    # --- Proba cada modelo ---
    print(f"=== Testando {len(CANDIDATOS)} IDs ===")
    disponiveis: list[str] = []
    nao_encontrados: list[str] = []
    outros: list[tuple[str, str]] = []

    for model_id in CANDIDATOS:
        sys.stdout.write(f"  {model_id:<55} ")
        sys.stdout.flush()
        try:
            controller = higgsfield_client.submit(
                application=model_id,
                arguments=ARGS_TESTE,
            )
            disponiveis.append(model_id)
            rid = getattr(controller, "request_id", "?")
            print(f"DISPONIVEL (request_id={rid})")
            if hasattr(controller, "cancel"):
                try:
                    controller.cancel()
                except Exception:
                    pass
        except Exception as exc:
            raw = str(exc)
            low = raw.lower()
            if "model not found" in low or ("model" in low and "not found" in low):
                nao_encontrados.append(model_id)
                print("nao encontrado")
            elif "not found" in low or "invalid" in low or "unknown" in low or "does not exist" in low:
                nao_encontrados.append(model_id)
                print(f"nao encontrado  [{raw[:60]}]")
            else:
                outros.append((model_id, raw))
                print(f"OUTRO ERRO → {raw[:80]}")

    # --- Resumo ---
    print()
    print("=" * 60)
    print("RESUMO")
    print("=" * 60)

    if disponiveis:
        print("MODELOS DISPONIVEIS NA SUA CONTA:")
        for m in disponiveis:
            print(f"  + {m}")
    else:
        print("NENHUM modelo confirmado como disponivel.")

    if outros:
        print("\nERROS INESPERADOS (mensagem completa):")
        for m, e in outros:
            print(f"  [{m}]")
            print(f"    {e}")

    print(f"\nNao encontrados: {len(nao_encontrados)}/{len(CANDIDATOS)}")
    print(f"Outros erros:   {len(outros)}/{len(CANDIDATOS)}")


if __name__ == "__main__":
    main()
