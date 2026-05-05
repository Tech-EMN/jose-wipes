# TUTORIAL PRÁTICO — José Wipes Pipeline

## Antes de tudo (uma vez só)

Abra o terminal e rode estes 2 comandos sempre que for usar o pipeline:

```bash
cd ~/jose-wipes-pipeline
source .venv/Scripts/activate
```

---

## FASE 1 — Testar e aprovar prompts (fazer ANTES de gerar vídeos)

### Ver status de todos os prompts

```bash
python scripts/testar_prompts.py --status
```

Vai mostrar uma tabela com 17 prompts e o score de cada um.

### Testar um prompt específico

Comece pelos de imagem (mais baratos e rápidos):

```bash
python scripts/testar_prompts.py --id img_01
```

O que acontece:
1. O sistema envia o prompt para a Higgsfield
2. Aguarda a geração (30s a 2min)
3. Baixa o resultado para a pasta output/
4. Pergunta sua nota (0-5)

Depois de rodar, abra o arquivo gerado:
- Imagens ficam em: output/teste_img_01.png
- Vídeos ficam em: output/teste_vid_ga_01.mp4

Olhe o resultado e volte no terminal para dar a nota.

### Ordem recomendada para testar

```bash
# IMAGENS PRIMEIRO (mais baratas, mais rápidas)
python scripts/testar_prompts.py --id img_01
python scripts/testar_prompts.py --id img_02
python scripts/testar_prompts.py --id vid_ga_05
python scripts/testar_prompts.py --id vid_trans_01

# DEPOIS VÍDEOS CURTOS
python scripts/testar_prompts.py --id vid_prod_01
python scripts/testar_prompts.py --id vid_prod_02
python scripts/testar_prompts.py --id vid_doc_01

# POR ÚLTIMO VÍDEOS COM PERSONAGENS (mais caros)
python scripts/testar_prompts.py --id vid_ga_01
python scripts/testar_prompts.py --id vid_ga_02
python scripts/testar_prompts.py --id vid_ga_04
```

### Se um prompt tirou nota baixa (1 ou 2)

1. Abra o arquivo: config/prompts_library.json
2. Encontre o prompt pelo ID (ex: "img_01")
3. Edite o campo "prompt" — adicione mais detalhes sobre o que faltou
4. Teste de novo:

```bash
python scripts/testar_prompts.py --id img_01
```

### Ver progresso geral

```bash
python scripts/testar_prompts.py --status
```

Meta: pelo menos 5 prompts com score 3 ou mais.

---

## FASE 2 — Gerar vídeos completos

Quando tiver prompts aprovados, rode o pipeline com um briefing:

### Vídeos simples (para começar)

```bash
python scripts/pipeline.py "Vídeo de 10 segundos mostrando o produto José Wipes em close, estilo premium, iluminação dramática. Para Instagram."
```

### Vídeo grupo de apoio (o principal)

```bash
python scripts/pipeline.py "Vídeo de 30 segundos estilo grupo de apoio. João confessa que usou papel, grupo reage chocado, líder revela José Wipes. Para Instagram Reels."
```

### Vídeo completo do roteiro principal (55 segundos)

```bash
python scripts/pipeline.py "Quero o vídeo completo do grupo de apoio, 55 segundos, 4 cenas. Cena 1: João confessa que usou papel, grupo reage chocado. Cena 2: Pedro conta história de festival, Carlos conta história de banheiro de estrada. Cena 3: Líder sereno de terno se levanta, coloca mão no ombro de João, diz que existe um caminho, tira pacote de wipes do bolso. Cena 4: Close no pacote, narração José Wipes a recuperação que você merece, texto na tela. Estilo paródia séria de AA, cinematográfico. Para todas as plataformas."
```

### Briefing livre (o sistema decide o formato)

```bash
python scripts/pipeline.py "Faz algo engraçado sobre banheiro de aeroporto"
```

### Usar um plano já gerado (sem gastar crédito do GPT de novo)

```bash
python scripts/pipeline.py --plano output/final/plano_20260407_010845.json
```

O que acontece quando roda:
1. GPT-4o decompõe seu briefing em cenas (30s)
2. Cada cena é gerada na Higgsfield (1-5 min por cena)
3. Áudio é gerado no ElevenLabs (poucos segundos)
4. FFmpeg junta tudo, adiciona logo e texto
5. Vídeo final aparece em output/final/

Tempo total: 10-20 minutos dependendo do número de cenas.

---

## FASE 3 — Avaliar qualidade (QA)

Depois de gerar alguns vídeos, rode a bateria de qualidade:

```bash
# Avaliar um briefing específico
python scripts/avaliar_qualidade.py --id qa_02

# Ver relatório de todas as avaliações
python scripts/avaliar_qualidade.py --relatorio
```

---

## COMANDOS ÚTEIS DO DIA A DIA

```bash
# Verificar se tudo está funcionando
python scripts/health_check.py

# Ver vozes configuradas
python scripts/clonar_vozes.py --status

# Ver estrutura do projeto
python scripts/mostrar_estrutura.py

# Rodar todos os testes
python tests/run_all.py
```

---

## ONDE FICAM OS ARQUIVOS

| O que | Onde |
|-------|------|
| Vídeos finais | output/final/*.mp4 |
| Cenas individuais | output/cenas/ |
| Planos JSON (roteiros) | output/final/plano_*.json |
| Testes de prompts | output/teste_*.png ou .mp4 |
| Testes de áudio | output/teste_voz_*.mp3 |
| Logs | logs/ |

---

## DICAS

- Comece SEMPRE testando prompts de imagem (mais barato)
- Briefings detalhados geram resultados melhores
- Se uma cena falhar no pipeline, ele continua com as outras
- O plano JSON fica salvo — pode re-rodar sem gastar crédito do GPT
- Guarde as notas dos scores — ajuda a refinar os prompts depois
