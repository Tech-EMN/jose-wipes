# HANDOFF — 2026-07-20 · Integração Sora-2 e Sora-2-Pro

**Autor:** Daedalus DEV (com Guilherme)
**Branch:** main (GitHub: Tech-EMN/jose-wipes)
**Status:** ✅ Código corrigido e deployado · ✅ API key configurada · ⏳ Aguardando teste em produção

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

## Commits (4 no total)

| Commit | Descrição |
|--------|-----------|
| `72cb146` | feat: Sora-2 (Padrão) e Sora-2-Pro (Profissional) — 5 arquivos |
| `c5acd74` | fix: `input_reference` com `ImageInputReferenceParam` + mensagens de erro específicas |
| `1114ba7` | docs: handoff inicial |
| `a2e8dd7` | fix: tamanhos Sora — sora-2 só suporta 720p (downgrade automático de 1080p) |

---

## Arquivos alterados

| Arquivo | O que |
|---------|-------|
| `webapp/video_generator.py` | Nova classe `OpenAISoraVideoGenerator` + factory com prefixo `openai:` + tamanhos por modelo |
| `webapp/schemas.py` | `VideoModelLiteral` expandido com `sora_2`, `sora_2_pro` |
| `webapp/model_registry.py` | Registro atualizado com 5 entradas (3 originais + 2 novas) |
| `templates/index.html` | Dropdown do Web Studio atualizado |
| `static/app.js` | Hints dos modelos atualizados |

---

## Regras de tamanho por modelo

| Cenário | sora-2 | sora-2-pro |
|---------|--------|------------|
| 9:16 720p | `720x1280` | `720x1280` |
| 9:16 1080p | ⚠️ downgrade → `720x1280` | `1024x1792` |
| 16:9 720p | `1280x720` | `1280x720` |
| 16:9 1080p | ⚠️ downgrade → `1280x720` | `1792x1024` |

### Limitação de duração

- Sora suporta: **4, 8 ou 12 segundos**
- Shots do planner: **5 segundos**
- Adapter arredonda automaticamente para **4 segundos**
- Diferença de 1s absorvida pelo FFmpeg

---

## ⚠️ Pré-requisito: API Key da OpenAI

A `OPENAI_API_KEY` do `.env` precisa ter o scope **`api.videos.write`**.

**Status:** ✅ Guilherme configurou Videos = Write em 2026-07-20 (key Restricted, sem alterar outros scopes).

**Nota EBI:** Este procedimento de auth externa não está documentado no EBI/ATRIA. Pendente migrar para `MANUAL_OPERACAO.md`.

---

## Erros tratados

| Código | Retryable | Gatilho | Mensagem |
|--------|-----------|---------|----------|
| `sora_auth_error` (401) | ❌ Não | Scope ausente | "Adicione o scope api.videos.write" |
| `sora_rate_limit` (429) | ✅ Sim | Limite excedido | "Limite de requisições atingido" |
| `sora_api_error` (400) | ✅ Sim | Tamanho inválido, etc. | Inclui erro real da API (até 200 chars) |
| `sora_download_error` | ✅ Sim | Falha no download | "Vídeo gerado mas falha no download" |
| `no_api_key` | ❌ Não | Chave ausente | "OPENAI_API_KEY não configurada" |

---

## Teste rápido

1. Acessar o Web Studio (Hostinger)
2. Selecionar tier **"Sora-2 — Padrão"**
3. Prompt curto: `"Vídeo de 10 segundos, fundo branco, produto centralizado"`
4. Resolução 720p (ou 1080p — downgrade automático)
5. Verificar se o job completa sem erro

---

## Pendências

- [ ] Testar Sora-2 em produção (após redeploy com `a2e8dd7`)
- [ ] Testar Sora-2-Pro em produção
- [ ] Migrar procedimento de API key do handoff para `MANUAL_OPERACAO.md`
- [ ] Avaliar se MiniMax também deve ser integrado (já configurado no gateway)
- [ ] Rodar `descobrir_modelos_higgsfield.py` no servidor de produção para verificar novos modelos
