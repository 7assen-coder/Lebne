# Dataset schema (Lebne)

## Training JSONL (`data/datasets/*.jsonl`)

Each line is one object:

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | Stable unique id |
| `intent` | string | `expense_extraction` \| `faq` \| `account_action` \| `clarify` \| `out_of_domain` |
| `locale` | string | `ar` \| `fr` \| `en` (product); crowdsourced files may also use `hassaniya` |
| `reviewed` | bool | Must be `true` before training |
| `split` | string | `train` \| `val` \| `test` |
| `messages` | array | Chat turns `{role, content}` |

Validate:
```bash
python scripts/validate_dataset.py data/datasets/sample_train.jsonl
python scripts/validate_dataset.py data/datasets/imported_banking.jsonl
# Before fine-tune:
python scripts/validate_dataset.py data/datasets/sample_train.jsonl --require-reviewed
```

### Intent mapping (public banking → Lebne)

| Source-ish intents | Lebne `intent` |
|--------------------|----------------|
| balance, transfer status, card, fees, exchange… (info) | `faq` |
| change PIN/password/phone, freeze, activate… | `account_action` |
| spent X MRU at shop (hand-written) | `expense_extraction` |
| greetings / vague | `clarify` |
| non-banking | `out_of_domain` |

Import public sets (EN Banking77 + ArBanking77 MSA + DarijaBanking EN/FR/MSA):
```bash
python scripts/import_banking_datasets.py
python scripts/review_imported_sample.py   # marks ~50/locale reviewed=true
```

Lebne expense examples: `data/datasets/lebne_expenses.jsonl`.

### Crowdsourced Mauritanian rewrites

Website: `/contrib/` (see [docs/contrib-deploy.md](../docs/contrib-deploy.md)).

- Seed queue: `imported_banking.jsonl` (read-only) → `python scripts/seed_contrib_queue.py`
- Contributors rewrite into natural Mauritanian e-wallet speech (not literal MT)
- Admin approves → separate files:

  - `lebne_mru_en.jsonl`
  - `lebne_mru_fr.jsonl`
  - `lebne_mru_ar.jsonl`
  - `lebne_mru_hassaniya.jsonl`

`lebne_mru_hassaniya.jsonl` expands each approved rewrite into **up to three** training
rows (EN / FR / AR user turns → same Hassaniya assistant) so the model can answer when
the client asks in any of those languages. Web download fills missing views via cached/MT
when possible (`X-Lebne-Export-Expanded: en,fr,ar`).

```bash
python scripts/export_mru_locale_jsonl.py                 # source + cached views only
python scripts/export_mru_locale_jsonl.py --fill-missing-views  # same as web download
```

## FAQ JSONL (`data/faq/faq.jsonl`)

| Field | Type |
|-------|------|
| `id` | string |
| `locale` | string (`ar` \| `fr` \| `en`) |
| `question` | string |
| `answer` | string |
| `version` | int |

Product FAQ stays AR/FR/EN. Hassaniya belongs in crowdsourced training files, not FAQ, until product support is explicit.

Reindex after edits:
```bash
python scripts/index_faq.py --recreate
```

## Long-term data plan
1. Grow FAQ coverage (KYC, fees, corridors, disputes) in **AR / FR / EN**.
2. Grow Mauritanian rewrites (incl. Hassaniya) via `/contrib/` into `lebne_mru_*.jsonl`.
3. Keep `reviewed=false` rows out of training until QA.
4. After each fine-tune, run `scripts/run_eval.py`.
