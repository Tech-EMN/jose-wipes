# HANDOFF — 2026-07-20 · Integração Sora-2 e Sora-2-Pro

**Autor:** Daedalus DEV (com Guilherme)
**Branch:** main (GitHub: Tech-EMN/jose-wipes)
**Status:** ✅ Código deployado · ⏳ Aguardando propagação da permissão na API key

---

## O que foi feito

O Web Studio do José Wipes tinha 3 tiers de vídeo que apontavam todos para o mesmo modelo (Kling 2.1 via Higgsfield). Adicionamos **dois novos backends reais** usando a `OPENAI_API_KEY` que já existia no `.env`.

### Modelos antes

| Tier | Modelo | Backend |
|------|--------|---------|
| Padrão | Kling 2.1 | Higgsfield |
| Realista | Kling 2.1 | Higgsfield |
| Profissional | Kling 2.1 | Higgsfield |

### Modelos depois

| Tier | Dropdown | Modelo Real | Backend |
|------|----------|-------------|---------|
| ⚡ Padrão | Sora-2 — Padrão | `openai:sora-2` | OpenAI (OPENAI_API_KEY) |
| 🎬 Realista | Kling 2.1 — Realista | `kling-video/v2.1/...` | Higgsfield (HF_API_KEY) |
| 👑 Profissional | Sora-2-Pro — Profissional | `openai:sora-2-pro` | OpenAI (OPENAI_API_KEY) |

---

## Arquivos alterados

| Arquivo | Commit | O que |
|---------|--------|-------|
| `webapp/video_generator.py` | `72cb146` + `c5acd74` | Nova classe `OpenAISoraVideoGenerator` + factory com prefixo `openai:` |
| `webapp/schemas.py` | `72cb146` | `VideoModelLiteral` expandido com `sora_2`, `sora_2_pro` |
| `webapp/model_registry.py` | `72cb146` | Registro atualizado com 5 entradas |
| `templates/index.html` | `72cb146` | Dropdown do Web Studio atualizado |
| `static/app.js` | `72cb146` | Hints dos modelos atualizados |

### Como funciona o roteamento (`video_generator.py`)

```python
application.startswith("openai:")  → OpenAISoraVideoGenerator
else                               → HiggsfieldVideoGenerator
```

### Limitação do Sora

- Sora suporta durações: **4, 8 ou 12 segundos**
- Os shots do planner são de **5 segundos**
- O adapter arredonda automaticamente para **4 segundos**
- A diferença de 1s é absorvida pelo FFmpeg na composição final

---

## ⚠️ Pré-requisito: API Key da OpenAI

A `OPENAI_API_KEY` do `.env` precisa ter o scope **`api.videos.write`**.

**Status:** Guilherme alterou a key para Restricted com Videos = Write em 2026-07-20. Aguardando propagação (~2 minutos).

Se o erro `401 — Missing scopes: api.videos.write` persistir, verificar:
1. Se o scope foi salvo corretamente
2. Se o projeto OpenAI vinculado à key tem Sora habilitado

---

## Erros tratados

| Código | Retryable | Mensagem |
|--------|-----------|----------|
| `sora_auth_error` (401) | ❌ Não | "Adicione o scope api.videos.write" |
| `sora_rate_limit` (429) | ✅ Sim | "Limite de requisições atingido" |
| `sora_api_error` (genérico) | ✅ Sim | Inclui o erro real da API (até 200 chars) |
| `no_api_key` | ❌ Não | "OPENAI_API_KEY não configurada" |

---

## Teste rápido

Depois que a permissão propagar, gerar um vídeo simples pelo Web Studio:

1. Acessar o Web Studio (Hostinger)
2. Selecionar tier **"Sora-2 — Padrão"**
3. Prompt curto: `"Vídeo de 10 segundos, fundo branco, produto centralizado"`
4. Verificar se o job completa sem erro 401

---

## Pendências

- [ ] Confirmar que Sora-2 funciona após propagação da permissão
- [ ] Documentar procedimento de API key no MANUAL_OPERACAO.md
- [ ] Avaliar se MiniMax também deve ser integrado (já configurado no gateway)
- [ ] Rodar `descobrir_modelos_higgsfield.py` no servidor de produção para verificar novos modelos
