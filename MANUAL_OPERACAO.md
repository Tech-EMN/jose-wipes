# Manual de Operação — José Wipes Pipeline

## O que é isto

Este sistema transforma briefings em texto em vídeos comerciais da marca José Wipes usando inteligência artificial. Você escreve o que quer ("faz um vídeo de grupo de apoio de 30 segundos"), o sistema gera o roteiro, cria as cenas, monta o áudio e entrega o vídeo final pronto.

## Critérios de entrega

Um job só termina como `completed` quando:

- todas as cenas planejadas foram geradas e compostas;
- narração, embalagem e textos solicitados foram aplicados;
- o MP4 final possui H.264, áudio AAC, duração válida e a resolução escolhida;
- a saída vertical em 1080p mede exatamente `1080x1920`;
- em jobs Higgsfield 1080p, o arquivo bruto do provedor também precisa medir `1080x1920` antes da composição; upscale não é aceito como prova;
- quando `JW_DRIVE_REQUIRED=true`, o upload para o Google Drive foi concluído.

Falha em qualquer etapa obrigatória encerra o job como `failed`. A meta operacional do desafio é concluir cada vídeo em até 20 minutos e comprovar pelo menos 80% de sucesso em uma amostra mínima de 10 jobs.

Enquanto a Atria não confirmar se o Drive é obrigatório, `JW_DRIVE_REQUIRED=false` mantém o download pelo Studio como entrega válida. O sistema ainda tenta enviar ao Drive quando ele está configurado; uma falha nesse envio gera aviso, mas preserva o vídeo local.

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
4. Aguarde a conclusão, com meta máxima de 20 minutos
5. O vídeo final estará em `output/final/` para download e, quando configurado, no Google Drive

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
- O job falha sem publicar um vídeo parcial
- Falhas de rede durante o polling do Higgsfield consultam novamente o mesmo `request_id`, sem criar uma geração duplicada
- Tente novamente em alguns minutos

### 4. "JSON inválido do planner"
- Raro, mas pode acontecer
- Rode novamente — o resultado é diferente a cada vez
- Se persistir, simplifique o briefing

---

## Custos mensais estimados

| Serviço | Custo | Uso |
|---|---|---|
| Higgsfield | US$ 9-119/mês | Geração de vídeo/imagem |
| ElevenLabs | US$ 22/mês | Vozes e áudio |
| OpenAI | Variável por uso | Planejamento de briefings e tiers Sora |
| Google Cloud | Grátis (uso baixo) | Storage no Drive |
| **Total** | **~US$ 50-190/mês** | |

---

## Verificar saúde do sistema

```bash
python scripts/health_check.py
```

## Google Drive OAuth para uso local

Para autorizar uma conta pessoal do Google somente no ambiente local:

1. coloque o cliente OAuth em `credentials/google-oauth-client.json` ou ajuste `GOOGLE_OAUTH_CLIENT_FILE`;
2. execute `python -m scripts.google_drive_auth`;
3. conclua a autorização no navegador;
4. preserve o token gerado em `credentials/google-oauth-token.json` ou ajuste `GOOGLE_OAUTH_TOKEN_FILE`.

Os arquivos OAuth e o token não devem ser enviados ao Git. Em Windows, mantenha a pasta `credentials` com acesso restrito ao usuário da aplicação; em sistemas POSIX, o token é gravado com modo `0600`.

## Deploy em produção no EasyPanel

O fluxo atual usa GitHub Actions e o Deployment Trigger URL do EasyPanel. Consulte `EASYPANEL_DEPLOY.md`.

`HOSTINGER_DEPLOY.md`, `docker-compose.hostinger.yml` e `.env.hostinger.example` permanecem apenas como alternativa legada.

## Contato suporte

ATRIA Corp — equipe responsável pelo pipeline.
