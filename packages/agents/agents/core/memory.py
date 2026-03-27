"""
agents.core.memory — MemoryAgent: extracts facts worth persisting across sessions (LLM).

Migrated from packages/api/src/api/modules/agent/agents/memory_agent.py.
Import path changes:
  api.modules.agent.schemas.sub_agents -> agents.orchestrator.schemas
  (shared.* imports are unchanged)
"""

from __future__ import annotations

import json

from agents.orchestrator.schemas import (
    ExtractedFact,
    MemoryInput,
    MemoryOutput,
)
from shared.llm.base import BaseLLM
from shared.logging import get_logger
from shared.schemas import AgentInput
from shared.utils import strip_markdown_code_block

__all__ = ["MemoryAgent"]

logger = get_logger(__name__)

_EMPTY_OUTPUT = MemoryOutput(facts=[], summary_for_storage="")

_VALID_CATEGORIES = {"decision", "topic", "preference", "open_question", "other"}
_VALID_IMPORTANCE = {"high", "medium", "low"}


class MemoryAgent:
    """Extracts facts worth persisting across sessions using an LLM."""

    def __init__(self, *, llm: BaseLLM) -> None:
        self._llm = llm

    def run(self, input: MemoryInput) -> MemoryOutput:
        prompt = self._build_prompt(input)
        ai_response = self._llm.generate(
            AgentInput(user_message=prompt, session_id=input.session_id, history=[]),
            response_mode="json",
        )
        raw_content = ai_response.content
        try:
            data = json.loads(strip_markdown_code_block(raw_content))
            raw_facts = data.get("facts", [])
            facts = []
            for f in raw_facts:
                category = f.get("category", "other")
                if category not in _VALID_CATEGORIES:
                    category = "other"
                importance = f.get("importance", "medium")
                if importance not in _VALID_IMPORTANCE:
                    importance = "medium"
                facts.append(
                    ExtractedFact(
                        category=category,  # type: ignore[arg-type]
                        fact=str(f.get("fact", "")),
                        importance=importance,  # type: ignore[arg-type]
                    )
                )
            return MemoryOutput(
                facts=facts,
                summary_for_storage=str(data.get("summary_for_storage", "")),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "MemoryAgent: failed to parse LLM response; returning empty output",
                extra={"error": str(exc)},
            )
            return _EMPTY_OUTPUT

    def _build_prompt(self, input: MemoryInput) -> str:
        return (
            f"CONVERSATION SUMMARY:\n{input.conversation_summary}\n\n"
            "Extract facts worth remembering for future sessions.\n"
            "Respond ONLY in this exact JSON format:\n"
            '{"facts": [{"category": "topic", "fact": "...", "importance": "medium"}], '
            '"summary_for_storage": "..."}'
        )
