"""
Unit tests for CritiqueAgent.
"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

import pytest

from app.modules.agent.schemas.sub_agents import CritiqueInput, RetrievedChunk
from app.modules.agent.agents.critique_agent import CritiqueAgent
from app.shared.llm.base import BaseLLM
from app.shared.schemas import AgentInput, AIResponse


# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------


class _FakeLLM(BaseLLM):
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.call_count = 0

    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AIResponse:
        idx = min(self.call_count, len(self._responses) - 1)
        self.call_count += 1
        return AIResponse(type="text", content=self._responses[idx])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk(id_: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=id_, score=0.9, text=text)


def _approved_json() -> str:
    return json.dumps(
        {
            "verdict": "approved",
            "confidence": 0.95,
            "verifications": [
                {
                    "claim": "Paris is the capital",
                    "supported": True,
                    "source_chunk_id": "c1",
                    "note": "",
                }
            ],
            "revision_instructions": "",
        }
    )


def _needs_revision_json() -> str:
    return json.dumps(
        {
            "verdict": "needs_revision",
            "confidence": 0.7,
            "verifications": [
                {
                    "claim": "London is the capital of France",
                    "supported": False,
                    "source_chunk_id": None,
                    "note": "Contradicted by source",
                }
            ],
            "revision_instructions": "Replace 'London' with 'Paris'.",
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_approved_verdict() -> None:
    agent = CritiqueAgent(llm=_FakeLLM([_approved_json()]))
    output = agent.run(
        CritiqueInput(
            question="Capital of France?",
            draft_answer="Paris is the capital of France.",
            chunks=[_chunk("c1", "France's capital is Paris.")],
            session_id="s1",
        )
    )

    assert output.verdict == "approved"
    assert output.confidence == 0.95
    assert len(output.verifications) == 1
    assert output.verifications[0].supported is True
    assert output.revision_instructions == ""


def test_needs_revision_verdict() -> None:
    agent = CritiqueAgent(llm=_FakeLLM([_needs_revision_json()]))
    output = agent.run(
        CritiqueInput(
            question="Capital of France?",
            draft_answer="London is the capital of France.",
            chunks=[_chunk("c1", "Paris is the capital of France.")],
            session_id="s1",
        )
    )

    assert output.verdict == "needs_revision"
    assert output.revision_instructions == "Replace 'London' with 'Paris'."
    assert output.verifications[0].supported is False
    assert output.verifications[0].source_chunk_id is None


def test_parse_failure_defaults_to_approved() -> None:
    agent = CritiqueAgent(llm=_FakeLLM(["not-valid-json {{{"]))
    output = agent.run(
        CritiqueInput(
            question="q",
            draft_answer="some answer",
            chunks=[],
            session_id="s1",
        )
    )

    # Safe default
    assert output.verdict == "approved"
    assert output.confidence == 0.6
    assert output.verifications == []


def test_no_chunks_still_calls_llm() -> None:
    llm = _FakeLLM([_approved_json()])
    agent = CritiqueAgent(llm=llm)
    agent.run(CritiqueInput(question="q", draft_answer="a", chunks=[], session_id="s1"))
    assert llm.call_count == 1


def test_strips_markdown_code_block() -> None:
    wrapped = "```json\n" + _approved_json() + "\n```"
    agent = CritiqueAgent(llm=_FakeLLM([wrapped]))
    output = agent.run(
        CritiqueInput(question="q", draft_answer="a", chunks=[], session_id="s1")
    )
    assert output.verdict == "approved"
