"""
agents.research.tools.summarizer — SummarizerTool.

Derived from synthesis_service.py: wraps the LLM synthesis logic as a standalone
BaseTool so it can be registered in a ToolRegistry and called by the action agent.
"""

from __future__ import annotations

from agents.core.tool import BaseTool, ToolExecutionError, ToolValidationError
from shared.llm.base import BaseLLM
from shared.logging import get_logger
from shared.schemas import AgentInput

__all__ = ["SummarizerTool"]

logger = get_logger(__name__)


class SummarizerTool(BaseTool):
    """Summarizes a block of text using the configured LLM."""

    name = "summarizer"
    description = (
        "Summarizes a block of text into a concise, natural-language summary. "
        "Use when the user asks for a summary or overview of provided content."
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to summarize",
            },
            "max_sentences": {
                "type": "integer",
                "description": "Target maximum number of sentences in the summary (1-10)",
                "minimum": 1,
                "maximum": 10,
                "default": 3,
            },
        },
        "required": ["text"],
    }

    def __init__(self, *, llm: BaseLLM) -> None:
        self._llm = llm

    def run(self, arguments: dict[str, object]) -> str:
        text = str(arguments.get("text", "")).strip()
        if not text:
            raise ToolValidationError(
                tool_id=self.name, validation_errors=["text is required"]
            )

        max_sentences_raw = arguments.get("max_sentences", 3)
        try:
            max_sentences = int(max_sentences_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            max_sentences = 3
        max_sentences = max(1, min(max_sentences, 10))

        prompt = (
            f"Summarize the following text in at most {max_sentences} sentences. "
            "Be concise and accurate. Do not add any information not present in the text.\n\n"
            f"TEXT:\n{text}"
        )

        try:
            response = self._llm.generate(
                AgentInput(user_message=prompt, session_id="summarizer", history=[])
            )
            return response.content.strip()
        except Exception as exc:
            raise ToolExecutionError(
                tool_id=self.name,
                reason=f"LLM call failed: {exc}",
                user_message="I was unable to summarize the provided text.",
            )
