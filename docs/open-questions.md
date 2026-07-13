# Open questions (ask before deep implementation)

1. **Wallet backend contract** — OpenAPI/URL for balance, transactions, password, phone? Auth scheme for service-to-service calls?
2. **Identity** — Who issues `user_id` / JWT? Existing API gateway in front of Lebne?
3. **Dialect data (deferred)** — Hassaniya corpus postponed; current scope is AR/FR/EN only.
4. **Hosting** — GPU cloud (for vLLM) preference: on-prem, AWS, GCP, other? Single-region Mauritania latency requirements?
5. **Confirmation UX** — How should the mobile app present confirmation / 2FA step-up when the agent returns `requires_confirmation` / `requires_2fa`?
6. **FAQ ownership** — Who updates `data/faq/faq.jsonl`, and what is the reindex cadence?
7. **Compliance** — Data residency / retention rules for chat logs and training feedback?
8. **Success metrics** — Target intent accuracy, FAQ groundedness, and max p95 latency for `/v1/chat`?

Do not implement beyond the scaffold until these are answered where they unblock security or model training.
