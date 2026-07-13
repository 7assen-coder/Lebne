"""FAQ / RAG agent stub."""

from __future__ import annotations

from typing import Any

from api.config import Settings
from api.llm_client import LLMClient
from api.security.chat_safety import build_llm_messages, filter_model_output, scrub_secrets
from rag.retriever import FaqRetriever


class FaqRagAgent:
    def __init__(self, llm: LLMClient, settings: Settings) -> None:
        self.llm = llm
        self.retriever = FaqRetriever(settings)

    async def run(self, message: str, history: list, *, user_id: str) -> dict[str, Any]:
        # user_id is for audit/isolation only — never embed into the model prompt.
        _ = user_id
        hits = await self.retriever.search(message, user_id=user_id)
        context = "\n\n".join(h["text"] for h in hits) if hits else "(no FAQ hits above threshold)"
        context, _ = scrub_secrets(context)
        messages = build_llm_messages(
            task_system=(
                "Answer only from FAQ context provided by the user message. "
                "If context is insufficient, say you do not know. Keep answers concise. "
                "Never invent fees or account balances."
            ),
            user_text=f"Context:\n{context}\n\nQuestion:\n{message}",
            history=history,
        )
        reply = await self.llm.chat(messages, temperature=0.2)
        reply, _ = filter_model_output(reply)
        return {"reply": reply, "metadata": {"rag_hits": hits}}
