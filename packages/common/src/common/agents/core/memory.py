"""Memory agent — distills conversation history into a compact memory."""
from __future__ import annotations

from common.infra.llm.base import BaseLLM


class MemoryAgent:
    """Summarises and stores key facts from a conversation turn."""

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

    def run(self, messages: list[dict]) -> str:
        """Return a concise memory string for the given message history."""
        prompt = (
            "Summarise the most important facts from this conversation in 3–5 bullet points."
        )
        result = self._llm.complete(prompt, history=messages)
        return result.content if hasattr(result, "content") else str(result)
