# Manual de Operação — José Wipes Pipeline

## O que é isto

Este sistema transforma briefings em texto em vídeos comerciais da marca José Wipes usando inteligência artificial. Você escreve o que quer ("faz um vídeo de grupo de apoio de 30 segundos"), o sistema gera o roteiro, cria as cenas, monta o áudio e entrega o vídeo final pronto.

---

## Como gerar um vídeo

### Passo a passo

1. Abra o terminal
2. Entre na pasta do projeto e ative o ambiente:
   ```bash
   cd ~/jose-wipes-pipeline
   source .venv/bin/activate       # Linux/Mac
   source .venv/Scripts/activate   # Windows
   ```
3. Rode o comando com seu briefing:
   ```bash
   python scripts/pipeline.py "Seu briefing aqui"
   ```
4. Espere 10-15 minutos
5. O vídeo final estará em `output/final/` e no Google Drive (se configurado)

### 4 exemplos prontos para copiar/colar

**Grupo de Apoio (30s):**
```bash
python scripts/pipeline.py "Vídeo de 30 segundos estilo grupo de apoio. João confessa que usou papel, grupo reage chocado, líder revela José Wipes. Para Instagram Reels."
```

**Product Demo Premium (15s):**
```bash
python scripts/pipeline.py "Vídeo de 15 segundos mostrando o produto em close, estilo premium, iluminação dramática. Narração curta. Para Instagram."
```

**Documentário (20s):**
```bash
python scripts/pipeline.py "Documentário de 20 segundos sobre banheiro de estádio. Narração dramática estilo documentário. Para TikTok."
```

**Briefing livre:**
```bash
python scripts/pipeline.py "Faz algo engraçado sobre banheiro de aeroporto"
```

---

## Dicas para briefings melhores

| Informação | Por que ajuda | Exemplo |
|---|---|---|
| Formato | Define o estilo visual | "estilo grupo de apoio" |
| Duração | Controla número de cenas | "30 segundos" |
| Plataforma | Otimiza formato | "para Instagram Reels" |
| Cenário | Detalha o ambiente | "no banheiro de estádio" |
| Ação | O que acontece | "João confessa, grupo reage" |
| Tom | Ajusta o humor | "paródia séria, sem pastelão" |

---

## O que NÃO precisa dizer

O sistema já sabe pelo brandbook:

- Formato 9:16 vertical (sempre)
- Paleta preto e branco para marca
- Não mostrar uso real do produto
- Incluir card final com logo e tagline
- Tom de humor seco e inteligente
- Descrever o produto corretamente
- Nomes e personalidades dos personagens

---

## Onde ficam os arquivos

| Pasta | Conteúdo |
|---|---|
| `output/final/` | Vídeos finais prontos (.mp4) e planos (.json) |
| `output/cenas/` | Cenas individuais (temporárias) |
| `config/` | Brandbook, prompts, vozes |
| `logs/` | Logs de geração por dia |
| `.env` | Chaves de API (NÃO compartilhar!) |

---

## Problemas comuns e soluções

### 1. "API key não configurada"
- Edite o arquivo `.env` na raiz do projeto
- Substitua os placeholders pelas chaves reais
- Rode `python scripts/health_check.py` para verificar

### 2. "FFmpeg não encontrado"
- Instale FFmpeg: https://ffmpeg.org/download.html
- No Windows: baixe, extraia e adicione ao PATH
- Verifique: `ffmpeg -version`

### 3. "Cena falhou na geração"
- Pode ser limite de API ou modelo ocupado
- O pipeline continua com as cenas que funcionaram
- Tente novamente em alguns minutos

### 4. "JSON inválido do Claude"
- Raro, mas pode acontecer
- Rode novamente — o resultado é diferente a cada vez
- Se persistir, simplifique o briefing

---

## Custos mensais estimados

| Serviço | Custo | Uso |
|---|---|---|
| Higgsfield | US$ 9-119/mês | Geração de vídeo/imagem |
| ElevenLabs | US$ 22/mês | Vozes e áudio |
| Anthropic (Claude) | US$ 20-50 (pay-per-use) | Decomposição de briefings |
| Google Cloud | Grátis (uso baixo) | Storage no Drive |
| **Total** | **~US$ 50-190/mês** | |

---

## Verificar saúde do sistema

```bash
python scripts/health_check.py
```

## Deploy em produção na Hostinger

Para subir a interface web com Docker Manager, Traefik, HTTPS, BasicAuth e volumes persistentes na Hostinger, use:

- `HOSTINGER_DEPLOY.md`
- `docker-compose.hostinger.yml`
- `.env.hostinger.example`

## Contato suporte

ATRIA Corp — equipe responsável pelo pipeline.
