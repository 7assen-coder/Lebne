# Slim API image: crowd + wallet + agent with hash embeddings (no torch).
# For real ST embeddings locally: pip install -e ".[embeddings]"
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY api ./api
COPY agent ./agent
COPY guardrail ./guardrail
COPY rag ./rag
COPY training ./training
COPY wallet ./wallet
COPY contrib ./contrib
COPY scripts ./scripts
COPY data ./data

# Install package without optional [embeddings] / [training] (keeps image small).
RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1
ENV LEBNE_EMBEDDING_BACKEND=hash

# Render/Fly inject PORT; local default 8000
ENV PORT=8000
EXPOSE 8000
# Single worker keeps memory under Render free limits; concurrency via async + Neon pool.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 30 --limit-concurrency 200"]
