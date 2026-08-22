# Deploy na Hostinger com Docker Manager + Traefik

Este projeto pode rodar de forma estavel na Hostinger usando um VPS Linux com o template Docker, Traefik para HTTPS e uma unica replica do app. O arquivo `docker-compose.hostinger.yml` foi criado para esse fluxo e preserva somente `output` e `logs` em volumes persistentes.

## O que este deploy assume

- VPS Hostinger do tipo KVM 2 ou superior
- Docker Manager habilitado no VPS
- subdominio apontando para o IPv4 do VPS, por exemplo `studio.seudominio.com`
- repositorio publico no GitHub
- uso interno, com autenticacao HTTP Basic na borda

## Arquivos relevantes

- `docker-compose.hostinger.yml`: compose de producao com Traefik, sem expor `8000`
- `.env.hostinger.example`: checklist das variaveis que precisam ser cadastradas no Docker Manager
- `scripts/cleanup_retention.py`: limpeza de jobs antigos e logs antigos
- `.github/workflows/hostinger-deploy.yml`: auto-deploy opcional via GitHub Actions

## 0. Publicar no GitHub

O fluxo recomendado e:

1. subir o codigo para o GitHub
2. fazer o primeiro deploy manual pelo Docker Manager com `Compose from URL`
3. opcionalmente ativar auto-deploy pelo workflow `.github/workflows/hostinger-deploy.yml`

Exemplo de comandos para um repositorio novo no GitHub:

```bash
git add .
git commit -m "Prepare Hostinger deployment"
git branch -M main
git remote add origin git@github.com:SEU_USUARIO/SEU_REPO.git
git push -u origin main
```

Depois do push, a URL raw do compose fica neste formato:

```text
https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPO/main/docker-compose.hostinger.yml
```

## 1. Preparar o VPS

1. Crie um VPS Linux na Hostinger com o template Docker.
2. No hPanel, ative a firewall e permita apenas `22`, `80` e `443`.
3. Nao publique a porta `8000`.
4. No Docker Manager, implante antes o projeto padrao de Traefik da propria Hostinger para criar a rede externa `traefik-proxy`.

## 2. Apontar o dominio

1. Crie um registro `A` para `studio.seudominio.com`.
2. Aponte esse registro para o IPv4 publico do VPS.
3. Aguarde a propagacao DNS antes de validar HTTPS.

## 3. Cadastrar variaveis no Docker Manager

Cadastre no projeto do app os valores de `.env.hostinger.example`:

- `TRAEFIK_HOST`
- `TRAEFIK_BASIC_AUTH_USERS`
- `HF_API_KEY`
- `HF_API_SECRET`
- `OPENAI_API_KEY`
- `OPENAI_PLANNER_MODEL=gpt-4.1-mini`
- `ELEVENLABS_API_KEY`
- `TZ`
- `PYTHONUNBUFFERED`

Para o upload no Shared Drive, adicione tambem:

- `GOOGLE_SERVICE_ACCOUNT_FILE=/app/credentials/service-account.json`
- `GOOGLE_DRIVE_FOLDER_ID` com o ID da pasta de destino no Shared Drive
- `GOOGLE_SERVICE_ACCOUNT_HOST_PATH=/opt/jose-wipes/credentials/service-account.json`

A Atria deve conceder à service account permissão para criar arquivos nessa pasta. O JSON deve existir no caminho do host antes do deploy e não deve ser enviado ao Git.

Para gerar `TRAEFIK_BASIC_AUTH_USERS`, crie um hash `htpasswd` e escape `$` como `$$` antes de colar no Docker Manager.

## 4. Publicar pelo Docker Manager

1. Escolha `Compose from URL`.
2. Aponte para o `raw` de `docker-compose.hostinger.yml` no GitHub.
3. Salve o projeto e rode o deploy.
4. Confirme que `GOOGLE_SERVICE_ACCOUNT_HOST_PATH` aponta para o JSON existente no VPS. O compose monta essa credencial somente no worker.

## 4.1 Repositorio privado

Se o repositorio for privado, use uma destas abordagens:

- criar uma deploy key no VPS e cadastrar no GitHub
- usar o workflow `.github/workflows/hostinger-deploy.yml` com `HOSTINGER_API_KEY` e `HOSTINGER_VM_ID`

Para deploy key no VPS, a Hostinger documenta este comando:

```bash
ssh-keygen -t ed25519 -C "my-repository" -N "" -f ~/.ssh/my-repository
```

Depois copie `~/.ssh/my-repository.pub` e adicione em `GitHub -> Settings -> Deploy Keys`.

## 4.2 Auto-deploy opcional com GitHub Actions

O workflow `.github/workflows/hostinger-deploy.yml` ja esta pronto para:

- rodar manualmente via `workflow_dispatch`
- rodar automaticamente a cada push na branch `main`
- pular sem falhar enquanto `HOSTINGER_API_KEY` ou `HOSTINGER_VM_ID` nao estiverem configurados
- fazer deploy usando `docker-compose.hostinger.yml`

No GitHub, configure:

### Secrets

- `HOSTINGER_API_KEY`
- `TRAEFIK_BASIC_AUTH_USERS`
- `HF_API_KEY`
- `HF_API_SECRET`
- `OPENAI_API_KEY`
- `ELEVENLABS_API_KEY`

### Variables

- `HOSTINGER_VM_ID`
- `TRAEFIK_HOST`
- `OPENAI_PLANNER_MODEL` (`gpt-4.1-mini`)
- `GOOGLE_SERVICE_ACCOUNT_FILE`
- `GOOGLE_DRIVE_FOLDER_ID`
- `GOOGLE_SERVICE_ACCOUNT_HOST_PATH`
- `TZ`
- `PYTHONUNBUFFERED`

Se quiser manter o repositorio privado e usar GitHub Actions, adicione tambem o token ou a estrategia de acesso exigida pela Hostinger conforme a documentacao oficial.

## 4.3 Botao "Deploy on Hostinger" opcional

Se quiser deixar um link de deploy rapido no repositório ou na documentacao, use este formato:

```md
[![Deploy on Hostinger](https://assets.hostinger.com/vps/deploy.svg)](https://www.hostinger.com/docker-hosting?compose_url=https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPO/main/docker-compose.hostinger.yml)
```

## 5. Validar o ambiente

Valide estes pontos apos o deploy:

1. `https://studio.seudominio.com/` responde com `200`.
2. A UI pede autenticacao basica antes de abrir.
3. `GET /api/health/external` retorna `ready_for_submit=true` quando as chaves e a conectividade estao corretas.
4. Um job simples de 10 segundos chega em `completed`.
5. O `download_url` baixa o MP4 final.
6. Reiniciar o container nao apaga jobs antigos nem logs.

## 6. Persistencia e operacao

O compose de producao usa somente estes volumes nomeados:

- `jose_wipes_output`
- `jose_wipes_logs`

Os assets de marca continuam embutidos na imagem e nao devem ser montados como volume vazio.

## 7. Retencao operacional

O script abaixo aplica a politica padrao do plano:

- jobs em `output/web_jobs` com mais de `30` dias
- logs em `logs/` com mais de `14` dias

Dry-run:

```bash
python scripts/cleanup_retention.py
```

Aplicar a limpeza:

```bash
python scripts/cleanup_retention.py --apply
```

Em producao, rode esse comando a partir do container ou via tarefa agendada no VPS.

## 8. O que nao muda

- A API continua igual: `/`, `/api/jobs`, `/api/jobs/{id}`, `/api/jobs/{id}/download`, `/api/health/external`
- O app continua ouvindo internamente em `8000`
- Continua existindo apenas uma instancia do worker, coerente com a fila atual baseada em disco

## Referencias oficiais

- Docker Manager: https://www.hostinger.com/support/12040815-how-to-deploy-your-first-container-with-hostinger-docker-manager/
- Traefik em multiplos projetos: https://www.hostinger.com/support/connecting-multiple-docker-compose-projects-using-traefik-in-hostinger-docker-manager/
- GitHub Actions para Hostinger: https://www.hostinger.com/support/deploy-to-hostinger-vps-using-github-actions/
- Repositorio privado com deploy key: https://www.hostinger.com/support/how-to-deploy-from-private-github-repository-on-hostinger-docker-manager/
