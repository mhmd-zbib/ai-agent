"""
MemoryAgent — extracts facts worth persisting across sessions (LLM).
"""
from __future__ import annotations

import json

from app.modules.agent.schemas.sub_agents import (
    ExtractedFact,
    MemoryInput,
    MemoryOutput,
)
from app.shared.llm.base import BaseLLM
from app.shared.logging import get_logger
from app.shared.schemas import AgentInput

logger = get_logger(__name__)

_EMPTY_OUTPUT = MemoryOutput(facts=[], summary_for_storage="")

_VALID_CATEGORIES = {"decision", "topic", "preference", "open_question", "other"}
_VALID_IMPORTANCE = {"high", "medium", "low"}


class MemoryAgent:
    def __init__(self, *, llm: BaseLLM) -> None:
        self._llm = llm

    def run(self, input: MemoryInput) -> MemoryOutput:
        prompt = self._build_prompt(input)
        ai_response = self._llm.generate(
            AgentInput(user_message=prompt, session_id=input.session_id, history=[])
        )
        raw_content = ai_response.content
        try:
            data = json.loads(self._strip_code_block(raw_content))
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

    def _strip_code_block(self, content: str) -> str:
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        return content
