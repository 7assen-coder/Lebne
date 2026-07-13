# Dataset schema (Lebne)

## Training JSONL (`data/datasets/*.jsonl`)

Each line is one object:

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | Stable unique id |
| `intent` | string | `expense_extraction` \| `faq` \| `account_action` \| `clarify` \| `out_of_domain` |
| `locale` | string | `ar` \| `fr` \| `en` only (Hassaniya deferred) |
| `reviewed` | bool | Must be `true` before training |
| `split` | string | `train` \| `val` \| `test` |
| `messages` | array | Chat turns `{role, content}` |

Validate:
```bash
python scripts/validate_dataset.py data/datasets/sample_train.jsonl
```

## FAQ JSONL (`data/faq/faq.jsonl`)

| Field | Type |
|-------|------|
| `id` | string |
| `locale` | string (`ar` \| `fr` \| `en`) |
| `question` | string |
| `answer` | string |
| `version` | int |

Reindex after edits:
```bash
python scripts/index_faq.py --recreate
```

## Long-term data plan
1. Grow FAQ coverage (KYC, fees, corridors, disputes) in **AR / FR / EN** only for now.
2. Hassaniya corpus is deferred — do not add dialect samples until explicitly requested.
3. Keep `reviewed=false` rows out of training until QA.
4. After each fine-tune, run `scripts/run_eval.py`.
