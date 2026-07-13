# Critical parameters

Single operational source: environment vars (`LEBNE_*`) via `api/config.py`.  
Training hyperparams: `training/train_qlora.py` → `QLoRAHyperParams`.

| Parameter | Current value | Location |
|-----------|---------------|----------|
| Base model | `Qwen/Qwen2.5-3B-Instruct` | `api/config.py` `base_model_name`; `training/train_qlora.py` |
| Served model name | `lebne-qwen2.5-3b` | `LEBNE_LLM_MODEL` / `api/config.py` |
| LLM provider | `vllm` | `LEBNE_LLM_PROVIDER` |
| LLM base URL | `http://localhost:8001/v1` | `LEBNE_LLM_BASE_URL` |
| Temperature | `0.1` | `LEBNE_LLM_TEMPERATURE` / `LLMClient.temperature` |
| Max tokens | `1024` | `LEBNE_LLM_MAX_TOKENS` |
| LoRA rank `r` | `16` | `training/train_qlora.py` |
| LoRA alpha | `32` | `training/train_qlora.py` |
| LoRA dropout | `0.05` | `training/train_qlora.py` |
| Learning rate | `2e-4` | `training/train_qlora.py` |
| Epochs | `3` | `training/train_qlora.py` |
| Embedding model | `paraphrase-multilingual-MiniLM-L12-v2` | `LEBNE_EMBEDDING_MODEL` |
| Qdrant collection | `lebne_faq` | `LEBNE_QDRANT_COLLECTION` |
| RAG top-k | `5` | `LEBNE_RAG_TOP_K` |
| RAG score threshold | `0.55` | `LEBNE_RAG_SCORE_THRESHOLD` |
| Chunk size / overlap | `256` / `32` | `LEBNE_CHUNK_SIZE` / `LEBNE_CHUNK_OVERLAP` |
| Guardrail threshold | `0.62` | `LEBNE_GUARDRAIL_THRESHOLD` (not calibrated yet) |
| Guardrail enabled | `true` | `LEBNE_GUARDRAIL_ENABLED` |

## Notes

- Temperature is intentionally low for a transactional wallet agent.  
- Guardrail threshold is a **placeholder** until calibrated on a labeled suite.  
- Export: production = merged HF weights for vLLM; GGUF optional for local Ollama only.
