# Lebne crowdsource web (React / Next.js → Vercel)

UI only. Data and auth live in the **Dockerized FastAPI + Postgres** stack (`/crowd/v1`).

1. **Register:** name → email → password  
2. **Contribute:** random phrases from the full ~45k queue (progress per user + locale)  
3. **Admin:** review with contributor name + email; approved rows append to `data/datasets/lebne_mru_*.jsonl` on the API host

## Prerequisites

```bash
# from repo root — Postgres + API
docker compose up -d postgres redis qdrant
docker compose up -d --build api
docker compose --profile seed run --rm seed
```

## Local web

```bash
cd web
cp .env.example .env
# API_INTERNAL_URL=http://127.0.0.1:8000

npm run dev
# http://localhost:3000
```

Register with the email set as `LEBNE_ADMIN_BOOTSTRAP_EMAIL` on the API to get **admin**.

## Vercel

1. Root Directory = `web` (not the monorepo root).
2. Deploy FastAPI + Postgres separately (private network preferred). Do **not** expose the API publicly if the BFF can reach it privately.
3. Env (Project → Settings → Environment Variables):

| Name | Notes |
|------|--------|
| `API_INTERNAL_URL` | HTTPS URL of FastAPI — **server-only**, never `NEXT_PUBLIC_` |
| `APP_URL` | Canonical public origin, e.g. `https://lebne.vercel.app` |
| `NEXT_PUBLIC_APP_URL` | Same as `APP_URL` (CSRF allowlist) |

4. Before first production traffic: confirm legacy contrib is off on the API (`LEBNE_CONTRIB_LEGACY_ENABLED=false`), strong `LEBNE_JWT_SECRET`, and bootstrap email only in private API env.
5. JSONL export lives on the API host (Vercel filesystem is ephemeral).

Security headers (CSP, HSTS, frame deny) ship from `next.config.ts`. Mutating routes use same-origin checks + httpOnly cookies.

## Scripts

```json
"dev": "next dev",
"build": "next build",
"start": "next start"
```
