# Lebne

Conversational AI agent for a Mauritanian e-wallet: expense extraction, FAQ/RAG, and gated account actions — in Arabic, French, English, and Hassaniya.

> Status: **Option A scaffold** — architecture, config, and stubs. Not production-ready yet.

## Linked repository

- GitHub: https://github.com/7assen-coder/Lebne.git
- Local: this workspace

## Production defaults (long-term)

| Concern | Choice | Why |
|--------|--------|-----|
| Backend | **FastAPI** (agent + wallet) | One secure control plane; Flutter is a client later |
| Mobile UI | Flutter (deferred) | Consumes JWT APIs only — not in current focus |
| LLM serving | **vLLM** (OpenAI-compatible) | Throughput, continuous batching, stable prod serving of HF weights |
| Local/dev override | Same client → Ollama `/v1` | No code fork for laptop debugging |
| Orchestration | LangGraph (stub runner today) | Explicit multi-agent routing |
| Vectors | Qdrant | Filtered retrieval, easy Docker ops |
| Sessions / step-up | Redis-ready | Durable sessions + one-time token jti |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` | Multilingual AR/FR/EN |
| Fine-tune | QLoRA on `Qwen/Qwen2.5-3B-Instruct` | Fits domain + low-resource dialect work |
| Inference temp | `0.1` | Transactional agent — low creativity |
| Deps / runtime | Python 3.11+, Docker Compose | Reproducible long-term ops |

## Quick start

```bash
cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d postgres redis qdrant
# optional FAQ index:
# LEBNE_EMBEDDING_BACKEND=hash python scripts/index_faq.py --recreate
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Auth (local):
- `POST /v1/auth/register` · `POST /v1/auth/login` (argon2)
- Dev only: `POST /v1/auth/dev-token` (disabled when `auth_mode=oidc` or production)

Production IdP: set `LEBNE_AUTH_MODE=oidc` + `LEBNE_OIDC_JWKS_URL` (see `docs/auth-password-idp.md`).

Chat: `POST /v1/chat` with `Authorization: Bearer <token>`.

## Layout

```text
api/          FastAPI, settings, LLM client, session store
agent/        LangGraph-oriented graph + specialized nodes
guardrail/    Domain gate (pre-LLM)
rag/          Chunking + Qdrant retriever stubs
training/     QLoRA + export stubs
data/         FAQ corpus + sample JSONL
eval/         Regression suite
scripts/      validate_dataset, index_faq, run_eval
docs/         Architecture, security, critical params
```

## Docs

- [Architecture](docs/architecture.md)
- [Security & ACL](docs/security.md)
- [Argon2 & IdP — purpose (deferred)](docs/auth-password-idp.md)
- [Chat prompt/output security](docs/chat-security.md)
- [Roadmap / where to go](docs/roadmap.md)
- [Critical parameters](docs/critical-params.md)
- [Open questions](docs/open-questions.md)

## License

Proprietary / TBD by repo owners.
