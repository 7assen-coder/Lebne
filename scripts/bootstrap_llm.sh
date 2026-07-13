#!/usr/bin/env bash
# Long-term local LLM bootstrap (macOS / laptop).
# Production servers should use vLLM + HF weights (see docs/model-ops.md).
set -euo pipefail

MODEL="${LEBNE_OLLAMA_MODEL:-qwen2.5:3b}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Install Ollama first: brew install ollama && brew services start ollama"
  exit 1
fi

if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "Starting Ollama..."
  brew services start ollama || true
  sleep 2
fi

echo "Pulling $MODEL (OpenAI-compatible at http://127.0.0.1:11434/v1)..."
ollama pull "$MODEL"

echo "Smoke chat completions..."
curl -sf http://127.0.0.1:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Say OK\"}],\"temperature\":0.1,\"max_tokens\":8}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["choices"][0]["message"]["content"])'

cat <<EOF

Configure Lebne (.env):
  LEBNE_LLM_PROVIDER=ollama
  LEBNE_LLM_BASE_URL=http://127.0.0.1:11434/v1
  LEBNE_LLM_MODEL=$MODEL
  LEBNE_LLM_TEMPERATURE=0.1

Production later: switch to vLLM on GPU host (same OpenAI-compatible client).
EOF
