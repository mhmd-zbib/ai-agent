"""
Unit tests for ReasoningAgent.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Optional


from app.modules.agent.schemas.sub_agents import ReasoningInput, RetrievedChunk
from app.modules.agent.agents.reasoning_agent import ReasoningAgent
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


def _chunk(id_: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=id_, score=0.9, text=text)


def _make_agent(responses: list[str]) -> tuple[ReasoningAgent, _FakeLLM]:
    llm = _FakeLLM(responses)
    return ReasoningAgent(llm=llm), llm


def _valid_json(
    answer: str = "Paris", adequacy: str = "sufficient", confidence: float = 0.95
) -> str:
    return json.dumps(
        {
            "answer": answer,
            "steps": [{"step_number": 1, "reasoning": "Step one reasoning"}],
            "context_adequacy": adequacy,
            "confidence": confidence,
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_parses_valid_json_response() -> None:
    agent, llm = _make_agent([_valid_json("The capital is Paris")])
    output = agent.run(ReasoningInput(question="What is the capital?", session_id="s1"))

    assert output.answer == "The capital is Paris"
    assert output.context_adequacy == "sufficient"
    assert output.confidence == 0.95
    assert len(output.steps) == 1
    assert llm.call_count == 1


def test_insufficient_context_flag() -> None:
    agent, _ = _make_agent(
        [_valid_json("Unknown", adequacy="insufficient", confidence=0.3)]
    )
    output = agent.run(ReasoningInput(question="What is X?", session_id="s1"))

    assert output.context_adequacy == "insufficient"
    assert output.confidence == 0.3


def test_invalid_json_fallback() -> None:
    agent, _ = _make_agent(["this is not json at all"])
    output = agent.run(ReasoningInput(question="Anything?", session_id="s1"))

    # Fallback: raw content as answer, insufficient, confidence=0.5
    assert output.answer == "this is not json at all"
    assert output.context_adequacy == "insufficient"
    assert output.confidence == 0.5
    assert output.steps == []


def test_chunks_appear_in_prompt() -> None:
    agent, llm = _make_agent([_valid_json()])
    chunks = [_chunk("c1", "France is in Europe"), _chunk("c2", "Paris is its capital")]
    agent.run(
        ReasoningInput(question="Capital of France?", chunks=chunks, session_id="s1")
    )

    assert "c1" in llm.last_prompt
    assert "France is in Europe" in llm.last_prompt
    assert "c2" in llm.last_prompt
    assert "Capital of France?" in llm.last_prompt


def test_no_chunks_builds_prompt_without_context_block() -> None:
    agent, llm = _make_agent([_valid_json()])
    agent.run(ReasoningInput(question="General question?", chunks=[], session_id="s1"))

    assert "CONTEXT:" not in llm.last_prompt
    assert "General question?" in llm.last_prompt


def test_strips_markdown_code_block() -> None:
    wrapped = "```json\n" + _valid_json("Answer wrapped") + "\n```"
    agent, _ = _make_agent([wrapped])
    output = agent.run(ReasoningInput(question="q?", session_id="s1"))

    assert output.answer == "Answer wrapped"


def test_multiple_reasoning_steps() -> None:
    data = {
        "answer": "42",
        "steps": [
            {"step_number": 1, "reasoning": "First step"},
            {"step_number": 2, "reasoning": "Second step"},
        ],
        "context_adequacy": "sufficient",
        "confidence": 0.8,
    }
    agent, _ = _make_agent([json.dumps(data)])
    output = agent.run(ReasoningInput(question="What is 6*7?", session_id="s1"))

    assert len(output.steps) == 2
    assert output.steps[0].step_number == 1
    assert output.steps[1].reasoning == "Second step"
