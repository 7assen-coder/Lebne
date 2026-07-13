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
- [x] Local LLM path: Ollama + `qwen2.5:3b` (prod remains vLLM)
- [x] Expanded FAQ + starter domain training JSONL

## Next (before Flutter)
1. Finish/verify `bash scripts/bootstrap_llm.sh` (model pulled)
2. Run API + smoke `POST /v1/chat` with Keycloak token
3. Grow reviewed AR/FR/EN datasets toward fine-tune size (Hassaniya deferred)
4. When GPU host ready: QLoRA → vLLM production serving
5. Alembic migrations (optional hardening)

## Last
- Flutter chat UI + confirm/2FA sheets + wallet screens
