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
├── scripts/
│   ├── __init__.py
│   ├── config.py                     # Configuração central + utilitários (Passo 2)
│   ├── system_prompt.py              # System prompt do Claude (Passo 7)
│   ├── gerador_midia.py              # Geração de vídeo/imagem/áudio (Passo 8)
│   ├── compositor.py                 # Composição FFmpeg (Passo 8)
│   ├── uploader.py                   # Upload Google Drive (Passo 8)
│   ├── pipeline.py                   # Orquestrador principal (Passo 8)
│   ├── testar_prompts.py             # Teste de prompts na Higgsfield (Passo 5)
│   ├── clonar_vozes.py               # Gerenciamento de vozes (Passo 6)
│   ├── avaliar_qualidade.py          # Bateria de QA (Passo 10)
│   ├── health_check.py               # Diagnóstico do sistema (Passo 10)
│   └── mostrar_estrutura.py          # Este arquivo (Passo 10)
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
