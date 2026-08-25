# Deploy no EasyPanel com GitHub Actions

Este é o fluxo de produção atual do José Wipes. O serviço `n8n / jose-wipes` usa o repositório `Tech-EMN/jose-wipes`, branch `main`, caminho de build `/` e o `Dockerfile` do projeto.

## Fluxo

1. Uma alteração é aprovada e mergeada na branch `main`.
2. O workflow `.github/workflows/easypanel-deploy.yml` executa os testes sem o marcador `e2e`.
3. Se os testes passarem, o workflow chama o Deployment Trigger URL do EasyPanel.
4. O EasyPanel busca a nova versão da `main`, constrói a imagem e substitui o serviço.
5. Se a variável opcional `APP_URL` estiver cadastrada no GitHub, o workflow valida `/api/health/external` após o gatilho.

## Configuração no GitHub

Em `Tech-EMN/jose-wipes`, abra `Settings → Secrets and variables → Actions`.

Cadastre o secret:

- `EASYPANEL_DEPLOY_URL`: Deployment Trigger URL copiado do serviço no EasyPanel.

Opcionalmente, cadastre a variável:

- `APP_URL`: URL pública do Studio sem barra final, por exemplo `https://studio.exemplo.com`.

O valor de `EASYPANEL_DEPLOY_URL` é uma credencial e não deve ser colocado em arquivos, logs, issues ou pull requests.

## Configuração no EasyPanel

Mantenha a origem do serviço apontando para:

- proprietário: `Tech-EMN`
- repositório: `jose-wipes`
- branch: `main`
- caminho de build: `/`
- construção: `Dockerfile`

O botão `Ativar Deploy Automático` deve permanecer desligado enquanto o GitHub Actions estiver ativo. Habilitar os dois mecanismos pode iniciar dois deploys para o mesmo merge.

As chaves das APIs e as demais variáveis de execução pertencem ao ambiente do serviço no EasyPanel. Elas não precisam ser copiadas para os secrets do GitHub Actions.

Antes do merge, configure um volume persistente em `/app/output`. Sem esse volume, cada substituição do container remove jobs, metadados e MP4s concluídos. Se o Google Drive estiver habilitado por arquivo, monte a credencial separadamente como secret somente leitura.

## Segurança e janela de deploy

Antes do merge, proteja o domínio do serviço com BasicAuth, SSO ou outra autenticação de borda no EasyPanel. `JW_AUTH_STRICT=false` somente é aceitável quando essa proteção externa já existe.

O worker do serviço App mantém a fila ativa em memória. Faça o merge somente quando não houver jobs em `queued`, `planning`, `generating`, `composing` ou `uploading_drive`; reiniciar o container durante um job pode interromper uma chamada paga.

O health externo valida apenas a presença das credenciais Higgsfield, sem upload, e reutiliza os demais probes por `JW_EXTERNAL_HEALTH_CACHE_SECONDS=300`, evitando chamadas repetidas a cada atualização da interface. Uma falha recente por falta de créditos bloqueia novas submissões Higgsfield por `JW_HIGGSFIELD_CREDIT_BLOCK_SECONDS=1800`; depois desse intervalo o operador pode testar novamente após repor os créditos.

## Execução e validação

O workflow pode ser iniciado automaticamente por push na `main` ou manualmente pela aba `Actions`. O modo manual permite ignorar os testes somente para uma emergência explícita.

Depois do primeiro merge, confirme:

1. os jobs `Run Tests` e `Deploy to EasyPanel` ficaram verdes;
2. apareceu uma nova implantação no histórico do serviço;
3. `GET /api/health/external` responde com HTTP `200`;
4. a aplicação continua gerando e disponibilizando o MP4 final.
5. um download concluído antes do deploy continua disponível depois da substituição do container.

O health check confirma apenas disponibilidade HTTP e pode responder pelo container anterior durante a troca. A revisão exata implantada deve ser confirmada no histórico do EasyPanel; o check não substitui o smoke test de geração de um job real.
