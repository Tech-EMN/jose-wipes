FROM python:3.12-slim

# Instalar FFmpeg (necessário para composição de vídeo)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements e instalar dependências primeiro (cache de layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo o projeto
COPY . .

# Criar diretórios necessários
RUN mkdir -p output/web_jobs output/cenas output/final logs credentials

# Expor a porta (Railway injeta $PORT automaticamente)
EXPOSE 8000

# Comando de início
CMD uvicorn webapp.main:app --host 0.0.0.0 --port ${PORT:-8000}
