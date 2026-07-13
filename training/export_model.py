"""Export fine-tuned weights for serving.

Production long-term: serve HF/safetensors with vLLM.
Optional: quantize to GGUF for local Ollama debugging only.
"""

from __future__ import annotations


def export_for_vllm(adapter_dir: str, out_dir: str) -> None:
    raise NotImplementedError(f"Merge LoRA adapter from {adapter_dir} into {out_dir} for vLLM")


def export_gguf(model_dir: str, out_file: str, quantization: str = "Q4_K_M") -> None:
    raise NotImplementedError(f"Export {model_dir} → {out_file} ({quantization}) for Ollama/dev")


if __name__ == "__main__":
    print("export_model.py stub — see docs/critical-params.md")
