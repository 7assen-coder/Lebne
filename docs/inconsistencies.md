# Doc vs code inconsistencies (honesty log)

| Claim | Reality in repo |
|-------|-----------------|
| "LangGraph orchestration" | Control flow is sequential in `agent/graph.py`; `StateGraph` not wired yet |
| "Qdrant RAG" | Client import attempted; search falls back to lexical FAQ samples |
| "Embedding guardrail" | Keyword-overlap stub; threshold not calibrated |
| "QLoRA trained model" | Hyperparams documented only; no training run artifacts |
| "vLLM in compose" | Service under profile `llm`; not required for API |
| "Production IdP" | Dev JWT mint at `/v1/auth/dev-token` — replace with real IdP |
| "Wallet persistence" | **Postgres/SQLite via SQLAlchemy** (`wallet/models.py`, `ledger_entries`) |
| Password hashing | Placeholder only — argon2 deferred (`docs/auth-password-idp.md`) |
| Production IdP | Dev JWT mint still exists in non-prod — IdP deferred |
| JWT / ACL / step-up | **Implemented** in `api/security/*` + `wallet/` |

Update this file whenever docs get ahead of implementation.
