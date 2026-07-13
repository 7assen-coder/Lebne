# Chat UI ↔ API security (brief)

Product shape: a **Cursor/Claude-like chat** (history + messages) talking to Lebne FastAPI.  
The model helps with expenses/FAQ; **account changes never execute inside the LLM**.

```text
Flutter/Web chat UI
   │  Bearer JWT (know the user)
   ▼
POST /v1/chat  + session history
   │
   ├─ 1. PROMPT protection   scrub secrets / injection notes → LLM only sees safe text
   ├─ 2. OUTPUT protection   scrub/block leaks before reply reaches UI
   └─ 3. USER + ACCOUNT      JWT identity, session isolation, WalletService ACL + step-up
```

## Measures

| Layer | What we protect | How |
|-------|-----------------|-----|
| **Prompt** | Secrets, tokens, passwords pasted in chat; prompt-injection | `sanitize_user_text` / `build_llm_messages` — redact before LLM; safety system preamble; history scrubbed |
| **Output** | Model leaking config/secrets/system prompt | `filter_model_output` on every assistant reply |
| **User data** | Cross-user history, PII in logs | Session keyed by JWT `sub`; log redaction; FAQ RAG is global product docs only |
| **Account** | Balance / password / phone abuse | Out of LLM: scopes + confirmation/2FA + `WalletService` |

## Rules of thumb
- UI may show the user their own chat history.
- LLM must **not** receive raw JWTs, API keys, or other users' data.
- “Knowing the user” = authenticated principal — not trusting fields inside the prompt text.
- Sensitive actions: chat can *request*; wallet APIs *execute* after step-up.

Implementation: `api/security/chat_safety.py` (wired in `agent/graph.py` + LLM nodes).
