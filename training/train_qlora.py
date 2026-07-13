"""
QLoRA fine-tuning entrypoint (stub).

Critical hyperparameters (source of truth until training is implemented):
  base_model: Qwen/Qwen2.5-3B-Instruct
  method: QLoRA (4-bit)
  lora_r: 16
  lora_alpha: 32
  lora_dropout: 0.05
  learning_rate: 2e-4
  num_train_epochs: 3
  export: GGUF for optional local Ollama; production serve via vLLM (HF/safetensors)

Do not invent results — run only when GPU + dataset are ready.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class QLoRAHyperParams:
    base_model: str = "Qwen/Qwen2.5-3B-Instruct"
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    learning_rate: float = 2e-4
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    max_seq_length: int = 2048
    bf16: bool = True


def main() -> None:
    params = QLoRAHyperParams()
    print("Lebne training stub — hyperparameters:")
    for key, value in asdict(params).items():
        print(f"  {key}: {value}")
    print("Implement PEFT/TRL loop here; do not start training without reviewed JSONL.")


if __name__ == "__main__":
    main()
