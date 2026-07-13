# Model operations (long-term)

## Strategy

| Environment | Serving | Model |
|-------------|---------|--------|
| Laptop / macOS (now) | **Ollama** OpenAI-compatible `/v1` | `qwen2.5:3b` |
| Production GPU | **vLLM** OpenAI-compatible `/v1` | Merged HF weights after QLoRA (`lebne-qwen2.5-3b`) |
| App code | One client: `api/llm_client.py` | Only `LEBNE_LLM_*` changes |

Do **not** commit model weights into git (`models/` is gitignored).

## Local bootstrap

```bash
brew install ollama
brew services start ollama
bash scripts/bootstrap_llm.sh
```

`.env` (local):
```bash
LEBNE_LLM_PROVIDER=ollama
LEBNE_LLM_BASE_URL=http://127.0.0.1:11434/v1
LEBNE_LLM_MODEL=qwen2.5:3b
LEBNE_LLM_TEMPERATURE=0.1
```

## Production (vLLM)

1. Fine-tune with `training/train_qlora.py` on reviewed JSONL.
2. Merge adapters → HF folder under `models/lebne-qwen2.5-3b` (on the GPU host).
3. `docker compose --profile llm up` (or managed vLLM).
4. Point API:
```bash
LEBNE_LLM_PROVIDER=vllm
LEBNE_LLM_BASE_URL=http://vllm:8000/v1
LEBNE_LLM_MODEL=lebne-qwen2.5-3b
```

## Dataset path to fine-tune quality
- Expand `data/faq/` + reindex Qdrant
- Expand reviewed `data/datasets/` (AR/FR/EN only for now)
- `python scripts/validate_dataset.py ...`
- `python scripts/run_eval.py` after each training iteration
