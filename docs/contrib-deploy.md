# Crowdsourcing site — deploy & ops

**Preferred app:** React / Next.js in [`web/`](../web/) → see [`web/README.md`](../web/README.md) for Vercel.

Legacy FastAPI Jinja UI (optional): `{PUBLIC_BASE_URL}/contrib/` · Admin: `{PUBLIC_BASE_URL}/admin/contrib`

## Local

```bash
cd /Users/medhasen/Projects/Lebne
source .venv/bin/activate
set -a && source .env && set +a

# Prefer a dedicated SQLite file so wallet and contrib don't fight schemas
export LEBNE_CONTRIB_DATABASE_URL=sqlite:///./lebne_contrib.db
export LEBNE_CONTRIB_ADMIN_PASSWORD='your-strong-password'
# optional voice:
# export LEBNE_OPENAI_API_KEY=sk-...

python scripts/seed_contrib_queue.py          # full ~45k (slow once)
# or: python scripts/seed_contrib_queue.py --limit 500

uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/contrib/

Approve items in `/admin/contrib` — each approval **appends** to:

- `data/datasets/lebne_mru_en.jsonl`
- `data/datasets/lebne_mru_fr.jsonl`
- `data/datasets/lebne_mru_ar.jsonl`
- `data/datasets/lebne_mru_hassaniya.jsonl`

Rebuild all four from the DB (idempotent overwrite):

```bash
python scripts/export_mru_locale_jsonl.py
python scripts/validate_dataset.py data/datasets/lebne_mru_fr.jsonl
```

## Render (shareable link)

1. Create a **Web Service** from this repo.
2. Add **Postgres** and set `LEBNE_DATABASE_URL` / `LEBNE_CONTRIB_DATABASE_URL` to the Render Postgres URL (`postgresql+psycopg://…`).
3. Set env:

| Variable | Value |
|----------|--------|
| `LEBNE_CONTRIB_ADMIN_PASSWORD` | strong secret |
| `LEBNE_PUBLIC_BASE_URL` | `https://your-service.onrender.com` |
| `LEBNE_OPENAI_API_KEY` | optional, for Whisper drafts |
| `LEBNE_ENV` | `production` |

4. Start command:

```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

5. After first deploy, run seed once (Render shell or one-off job):

```bash
python scripts/seed_contrib_queue.py
```

6. **Voice storage:** durable via `contrib_audio_assets` + Cloudflare R2 (set `LEBNE_R2_*`) or Neon payloads when R2 is unset. Do not rely on Render disk. Migrate legacy blobs once: `python scripts/migrate_audio_blobs_to_assets.py`. Clients use `audioId` (record / file picker on phone & laptop).

## Contributor instructions (short)

1. Read the **source** situation (from the 45k banking queue).
2. Pick AR / FR / EN / Hassaniya.
3. Write how a Mauritanian would ask that of **Lebne** (MRU, local speech) — not a literal translation.
4. Optional: hold mic / upload audio → edit the Whisper draft.
5. Submit → admin (you) approves into the locale fine-tune file.
