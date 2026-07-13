# Security & ACL

Lebne is a **FastAPI** backend (agent + wallet). Flutter is the future mobile client and is out of scope for this layer — it will only call JWT-protected HTTP APIs.

## Model

```text
Flutter (later) ──Bearer JWT──► FastAPI
                                 ├─ /v1/chat          (agent)
                                 ├─ /v1/security/*    (step-up)
                                 └─ /wallet/v1/*      (account mutations)
                                        │
                                        ▼
                                 WalletService (ACL + audit)
                                 Redis sessions / rate-limit / one-time jti
```

Rules:
- **Never trust client `user_id`** — identity comes from JWT `sub` only.
- LLM/agent **never** touches a database; only `WalletService` / `/wallet/v1` does.
- Sensitive actions require **signed, single-use** confirmation (± 2FA) tokens.

## Action controls

| Action | Scope | Sensitivity |
|--------|-------|-------------|
| `get_balance` | `wallet:balance:read` | authenticated |
| `list_transactions` | `wallet:transactions:read` | authenticated |
| `update_profile` | `wallet:profile:write` | confirmation token |
| `change_password` | `wallet:password:write` | confirmation + 2FA |
| `change_phone` | `wallet:phone:write` | confirmation + 2FA |

## What was closed (backend)

| Former gap | Status |
|------------|--------|
| Spoofable `X-User-Id` | **Closed** — Bearer JWT (`api/security/auth.py`) |
| No ACL scopes | **Closed** — roles/scopes (`api/security/acl.py`) + wallet checks |
| Confirm/2FA not crypto-verified | **Closed** — signed JWT step-up + single-use jti (`api/security/step_up.py`) |
| In-memory sessions only | **Mitigated** — Redis backend (`LEBNE_SESSION_BACKEND=redis`) |
| Weak PII redaction | **Improved** — phone/card/NNI/email/IBAN/JWT patterns |
| No rate limit | **Closed** — fixed window per user+IP |
| No audit trail | **Closed** — JSONL audit (`api/security/audit.py`) |

## Remaining (production hardening)

| Severity | Remaining work |
|----------|----------------|
| High | Replace HS256 shared secret with RS256/OIDC from real IdP |
| High | Real SMS/TOTP 2FA delivery (dev code peek must stay non-prod) |
| High | Postgres for wallet + argon2 password hashes (store is in-memory stub) |
| Medium | Embeddings-based domain guardrail (still keyword stub) |
| Medium | Encrypted log sinks / SIEM |
| Low | WAF / edge rate limits in front of API |

## Flutter contract (do not implement UI yet)

1. `POST /v1/auth/...` (IdP) → access token  
2. `Authorization: Bearer <token>` on all calls  
3. `POST /v1/chat` with `{session_id, message}` only  
4. If `requires_confirmation` / `requires_2fa`, complete `/v1/security/*` then retry chat with tokens  

Dev-only: `POST /v1/auth/dev-token` (disabled when `LEBNE_ENV=production`).
