"""OpenAI-compatible LLM client. Production default: vLLM."""

from __future__ import annotations

from typing import Any

import httpx

from api.config import Settings, get_settings


class LLMClient:
    """Thin client over an OpenAI-compatible chat completions API.

    Long-term production choice: **vLLM** (throughput, continuous batching,
    OpenAI-compatible surface). Local/dev can point the same client at Ollama
    (`/v1`) without changing call sites.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def temperature(self) -> float:
        # Transactional agent: keep temperature low and configurable in one place.
        return self.settings.llm_temperature

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.settings.llm_max_tokens,
        }
        if extra:
            payload.update(extra)

        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"

        # Stub-friendly: returns a clear placeholder if the server is down.
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001 — stub surface for Option A
            return (
                f"[LLM unavailable via {self.settings.llm_provider} at "
                f"{self.settings.llm_base_url}: {exc}]"
            )
