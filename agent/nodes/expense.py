"""Expense extraction agent stub."""

from __future__ import annotations

from typing import Any

from api.llm_client import LLMClient
from api.schemas import ChatMessage, ExpenseDraft
from api.security.chat_safety import build_llm_messages, filter_model_output


class ExpenseExtractionAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(self, message: str, history: list[ChatMessage]) -> dict[str, Any]:
        messages = build_llm_messages(
            task_system=(
                "Extract expense fields as JSON: amount, currency, merchant, category, date. "
                "Languages: ar, fr, en, hassaniya. If incomplete, ask one clarifying question. "
                "Do not request full card numbers or passwords."
            ),
            user_text=message,
            history=history,
        )
        draft_text = await self.llm.chat(messages, temperature=0.1)
        draft_text, _ = filter_model_output(draft_text)
        draft = ExpenseDraft(raw_text=message)
        return {
            "reply": draft_text,
            "metadata": {"expense_draft": draft.model_dump()},
        }
