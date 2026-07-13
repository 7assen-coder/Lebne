# Where to go next

Stack: FastAPI backend · Flutter UI **last**.

## Done
- [x] JWT + ACL + step-up + audit + rate limit + chat prompt/output safety
- [x] Postgres/SQLite wallet + ledger
- [x] Argon2id passwords + local register/login
- [x] Real IdP JWKS verification (`auth_mode=oidc|hybrid|local`)
- [x] LangGraph StateGraph agent runtime
- [x] Embedding guardrail + Qdrant FAQ indexer/retriever
- [x] Eval runner (`scripts/run_eval.py`)

## Next (before Flutter)
1. Point `LEBNE_OIDC_*` at your real IdP and test login
2. `docker compose up -d postgres redis qdrant` → `scripts/index_faq.py --recreate`
3. Serve model with vLLM (or Ollama locally) and set `LEBNE_LLM_*`
4. Run `scripts/run_eval.py` and expand FAQ/Hassaniya data
5. Alembic migrations (optional hardening)

## Last
- Flutter chat UI + confirm/2FA sheets + wallet screens
