# Step 1–2: IdP + infra

## Step 1 — IdP (done in repo)

Local **Keycloak** realm `lebne` is wired:

| Item | Value |
|------|--------|
| Admin UI | http://localhost:8080 (admin / admin) |
| Realm | `lebne` |
| Client | `lebne-api` (public, direct access grants) |
| Demo user | `demo` / `DemoPass123!` |
| JWKS | `http://localhost:8080/realms/lebne/protocol/openid-connect/certs` |
| Issuer | `http://localhost:8080/realms/lebne` |
| App mode | `LEBNE_AUTH_MODE=hybrid` in `.env` |

Get a token:
```bash
python scripts/keycloak_token.py
```

Production later: replace these URLs with your bank IdP and set `LEBNE_AUTH_MODE=oidc`.

## Step 2 — Postgres / Redis / Qdrant + FAQ index

### What you do (Docker must be running)

1. Start Docker Desktop and wait until it is ready.
2. From the project root:
```bash
cd /Users/medhasen/Projects/Lebne
docker compose up -d postgres redis qdrant keycloak
docker compose ps
```
3. Wait ~30–60s for Keycloak, then index FAQ:
```bash
source .venv/bin/activate
set -a && source .env && set +a
python scripts/index_faq.py --recreate
```
4. Check Qdrant collection:
```bash
curl -s http://localhost:6333/collections/lebne_faq | python -m json.tool
```

### What “done” looks like
- `postgres` on `:5432`, `redis` on `:6379`, `qdrant` on `:6333`, `keycloak` on `:8080`
- Collection `lebne_faq` exists with FAQ points
- Token from `scripts/keycloak_token.py` prints a long JWT
