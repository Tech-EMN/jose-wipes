"""Mostra a estrutura final do projeto José Wipes Pipeline."""

import sys
sys.stdout.reconfigure(encoding="utf-8")


ESTRUTURA = """
jose-wipes-pipeline/
├── .env                              # Chaves de API (Passo 1-2)
├── .gitignore                        # Proteção de arquivos sensíveis (Passo 2)
├── requirements.txt                  # Dependências Python (Passo 2)
├── MANUAL_OPERACAO.md                # Manual para o operador (Passo 10)
│
├── config/
│   ├── brandbook.json                # Memória digital da marca (Passo 4)
│   ├── prompts_library.json          # Biblioteca de prompts testados (Passo 5)
│   ├── vozes.json                    # Configuração de vozes ElevenLabs (Passo 6)
│   └── avaliacoes_qualidade.json     # Resultados de QA (Passo 10)
│
├── credentials/
│   └── google-service-account.json   # Service account Google Drive (Passo 1)
│
├── assets/
│   ├── logo/
│   │   └── logo_jose_wipes.png       # Logo da marca
│   ├── vozes/
│   │   ├── narrador/                 # Amostras para clonagem de voz
│   │   ├── joao/
│   │   └── lider/
│   └── referencias/                  # Vídeos de referência
│
├── jose_wipes/                       # Núcleo de domínio (importado pela web, worker e scripts)
│   ├── config.py                     # Configuração central + utilitários
│   ├── schemas.py                    # Contratos de request/plano/job
│   ├── model_registry.py             # Modelos de vídeo/imagem disponíveis
│   ├── moderation.py                 # Moderação de briefing
│   ├── pdf_utils.py                  # Leitura de roteiro em PDF
│   ├── retention.py                  # Limpeza de jobs e logs antigos
│   ├── runtime_state.py              # Estado do servidor local (output/runtime)
│   ├── logging_config.py             # Logging estruturado
│   ├── integrations/                 # Higgsfield, OpenAI, ElevenLabs, Drive, health
│   ├── composition/                  # FFmpeg, overlays, produto e referências
│   ├── planning/                     # Planner, narração e system prompt
│   ├── rendering/                    # pipeline_service: execução do plano
│   └── jobs/                         # JobManager, claim e recuperação de jobs
│
├── webapp/                           # App de produção: FastAPI, auth, rate limit, worker
│
├── scripts/                          # Ferramentas de linha de comando (chamam jose_wipes)
│   ├── pipeline.py                   # CLI do mesmo pipeline da web
│   ├── avaliar_qualidade.py          # Bateria de QA
│   ├── health_check.py               # Diagnóstico do sistema
│   ├── cleanup_retention.py          # Limpeza de jobs e logs
│   ├── web_server.py                 # Sobe/para o Studio localmente
│   ├── testar_prompts.py             # Teste de prompts na Higgsfield
│   ├── clonar_vozes.py               # Gerenciamento de vozes
│   ├── descobrir_modelos_higgsfield.py
│   ├── higgsfield_video_smoke_test.py
│   ├── google_drive_auth.py          # Autorização OAuth do Drive
│   └── mostrar_estrutura.py          # Este arquivo
│
├── tests/
│   ├── __init__.py
│   ├── run_all.py                    # Bateria completa de testes (Passo 3/10)
│   ├── test_ffmpeg.py                # Verifica FFmpeg instalado (Passo 2)
│   ├── test_higgsfield_image.py      # Teste de imagem Higgsfield (Passo 3)
│   ├── test_higgsfield_video.py      # Teste de vídeo Higgsfield (Passo 3)
│   ├── test_elevenlabs.py            # Teste ElevenLabs (Passo 3)
│   ├── test_gdrive.py                # Teste Google Drive (Passo 3)
│   ├── test_claude_decomposicao.py   # Teste Claude API (Passo 3)
│   ├── test_ffmpeg_composicao.py     # Teste composição FFmpeg (Passo 3)
│   ├── test_brandbook.py             # Validação brandbook (Passo 4)
│   ├── test_prompts_library.py       # Validação prompts (Passo 5)
│   ├── test_vozes.py                 # Validação vozes (Passo 6)
│   ├── test_system_prompt.py         # Validação system prompt (Passo 7)
│   └── test_pipeline.py             # Validação estrutural pipeline (Passo 8)
│
├── output/
│   ├── cenas/                        # Cenas individuais geradas
│   └── final/                        # Vídeos finais + planos JSON
│
├── logs/
│   └── geracao_YYYYMMDD.log          # Logs de geração
│
└── .venv/                            # Ambiente virtual Python
"""


def main():
    print("=" * 60)
    print("  ESTRUTURA DO PROJETO — José Wipes Pipeline")
    print("=" * 60)
    print(ESTRUTURA)


if __name__ == "__main__":
    main()
