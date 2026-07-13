# Architecture

## System diagram (intended runtime order)

```text
Client / Mobile App
        │
        ▼
API Gateway (auth, rate limits) ── X-User-Id ──► FastAPI `api/main.py`
                                                    │
                                                    ├─ PII-redacted logs
                                                    ├─ SessionStore (user_id, session_id)
                                                    ▼
                                            Domain Guardrail (`guardrail/`)
                                                    │
                         out-of-domain ─────────────┼──────────── in-domain
                                │                   ▼
                                ▼            Intent Router (`agent/nodes/router.py`)
                         safe refusal               │
                                      ┌─────────────┼─────────────┐
                                      ▼             ▼             ▼
                               ExpenseAgent     FaqRagAgent   AccountAgent
                               (extract JSON)   (Qdrant+LLM)  (backend APIs)
                                      │             │             │
                                      └─────────────┼─────────────┘
                                                    ▼
                                            ChatResponse (+ confirm/2FA flags)
```

## Components

| Component | Path | Role |
|-----------|------|------|
| API | `api/main.py` | HTTP surface, auth header check, session append |
| Settings | `api/config.py` | Single source for env-backed critical params |
| LLM client | `api/llm_client.py` | OpenAI-compatible client; **prod = vLLM** |
| Graph | `agent/graph.py` | Orchestration stub mirroring future LangGraph nodes |
| Router | `agent/nodes/router.py` | Intent classification |
| Expense | `agent/nodes/expense.py` | Structured expense extraction |
| FAQ | `agent/nodes/faq.py` | RAG over global FAQ (not per-user data) |
| Account | `agent/nodes/account.py` | ACL-gated backend calls only |
| Guardrail | `guardrail/domain.py` | Pre-LLM domain gate |
| Retriever | `rag/retriever.py` | top-k + score threshold |
| Training | `training/train_qlora.py` | QLoRA hyperparams + stub entry |
| Eval | `eval/test_suite.jsonl` | Non-regression cases |

## Conversation context

Current stub: **in-memory `SessionStore`** keyed by `(user_id, session_id)`.

Long-term: Redis (or equivalent) with TTL, optional sliding summary, strict user isolation. No cross-user RAG of private data — FAQ corpus is global product knowledge only.

## Serving strategy (production / long-term)

1. Fine-tune with QLoRA → merge adapters to HF/safetensors  
2. Serve with **vLLM** behind OpenAI-compatible `/v1/chat/completions`  
3. Keep GGUF/Ollama as **dev-only** path via the same client (`LEBNE_LLM_BASE_URL`)

## Data dependencies

```text
data/faq/faq.jsonl
    └─ scripts/index_faq.py ──► Qdrant collection `lebne_faq`
                                    └─ rag/retriever.py (query)

data/datasets/*.jsonl
    └─ scripts/validate_dataset.py ──► training/train_qlora.py
                                    └─ training/export_model.py ──► vLLM model dir

eval/test_suite.jsonl
    └─ scripts/run_eval.py ──► CI gate after each fine-tune
```

## What is still stubbed (not invented as done)

- Real LangGraph `StateGraph` wiring  
- Real embedding similarity guardrail  
- Real Qdrant upsert/search  
- Real PEFT training loop  
- Wallet backend integration  
- Redis session memory  
- Production ACL service
