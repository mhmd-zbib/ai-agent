"""
Unit tests for MemoryAgent.
"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

import pytest

from app.modules.agent.schemas.sub_agents import MemoryInput
from app.modules.agent.agents.memory_agent import MemoryAgent
from app.shared.llm.base import BaseLLM
from app.shared.schemas import AgentInput, AIResponse


# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------


class _FakeLLM(BaseLLM):
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.call_count = 0
        self.last_prompt: str = ""

    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AIResponse:
        self.last_prompt = payload.user_message
        idx = min(self.call_count, len(self._responses) - 1)
        self.call_count += 1
        return AIResponse(type="text", content=self._responses[idx])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_memory_json() -> str:
    return json.dumps(
        {
            "facts": [
                {"category": "preference", "fact": "User prefers Python.", "importance": "high"},
                {"category": "topic", "fact": "Discussed RAG pipelines.", "importance": "medium"},
            ],
            "summary_for_storage": "User is a Python developer exploring RAG.",
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_facts_extracted_correctly() -> None:
    agent = MemoryAgent(llm=_FakeLLM([_valid_memory_json()]))
    output = agent.run(
        MemoryInput(session_id="s1", conversation_summary="We talked about Python and RAG.")
    )

    assert len(output.facts) == 2
    assert output.facts[0].category == "preference"
    assert output.facts[0].fact == "User prefers Python."
    assert output.facts[0].importance == "high"
    assert output.facts[1].category == "topic"
    assert output.summary_for_storage == "User is a Python developer exploring RAG."


def test_parse_failure_returns_empty_output() -> None:
    agent = MemoryAgent(llm=_FakeLLM(["garbage not json"]))
    output = agent.run(MemoryInput(session_id="s1", conversation_summary="anything"))

    assert output.facts == []
    assert output.summary_for_storage == ""


def test_conversation_summary_appears_in_prompt() -> None:
    llm = _FakeLLM([_valid_memory_json()])
    agent = MemoryAgent(llm=llm)
    agent.run(MemoryInput(session_id="s1", conversation_summary="User asked about Python."))

    assert "User asked about Python." in llm.last_prompt


def test_strips_markdown_code_block() -> None:
    wrapped = "```json\n" + _valid_memory_json() + "\n```"
    agent = MemoryAgent(llm=_FakeLLM([wrapped]))
    output = agent.run(MemoryInput(session_id="s1", conversation_summary="summary"))

    assert len(output.facts) == 2


def test_invalid_category_defaults_to_other() -> None:
    data = {
        "facts": [
            {"category": "unknown_cat", "fact": "Some fact.", "importance": "high"},
        ],
        "summary_for_storage": "brief",
    }
    agent = MemoryAgent(llm=_FakeLLM([json.dumps(data)]))
    output = agent.run(MemoryInput(session_id="s1", conversation_summary="s"))

    assert output.facts[0].category == "other"


def test_invalid_importance_defaults_to_medium() -> None:
    data = {
        "facts": [
            {"category": "topic", "fact": "A fact.", "importance": "ultra"},
        ],
        "summary_for_storage": "brief",
    }
    agent = MemoryAgent(llm=_FakeLLM([json.dumps(data)]))
    output = agent.run(MemoryInput(session_id="s1", conversation_summary="s"))

    assert output.facts[0].importance == "medium"
