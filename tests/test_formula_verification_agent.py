"""Tests for FormulaVerificationAgent."""

from __future__ import annotations

import json
from typing import Any, Literal, Optional
from unittest.mock import MagicMock

import pytest

from app.modules.agent.agents.formula_verification_agent import FormulaVerificationAgent
from app.modules.agent.schemas.sub_agents import (
    FormulaVerificationInput,
    FormulaVerificationOutput,
    RetrievedChunk,
)
from app.shared.llm.base import BaseLLM
from app.shared.schemas import AgentInput, AIResponse


class _FakeLLM(BaseLLM):
    def __init__(self, content: str) -> None:
        self._content = content

    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call", "json"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AIResponse:
        # AIResponse requires min_length=1 on content
        return AIResponse(type="text", content=self._content if self._content else "{ }")


def _make_llm(content: str) -> _FakeLLM:
    return _FakeLLM(content)


# ---------------------------------------------------------------------------
# Happy path — verified
# ---------------------------------------------------------------------------


def test_run_returns_verified_on_correct_formula() -> None:
    payload = json.dumps(
        {
            "verdict": "verified",
            "confidence": 0.97,
            "explanation": "KE = 0.5 * m * v**2 is correct.",
            "corrected_formula": None,
        }
    )
    agent = FormulaVerificationAgent(llm=_make_llm(payload))
    output = agent.run(
        FormulaVerificationInput(
            session_id="s1",
            problem="Calculate kinetic energy",
            formula="0.5 * m * v**2",
            variables={"m": 5.0, "v": 10.0},
        )
    )
    assert output.verdict == "verified"
    assert output.confidence == pytest.approx(0.97)
    assert output.corrected_formula is None
    assert "correct" in output.explanation


# ---------------------------------------------------------------------------
# Happy path — needs revision with corrected formula
# ---------------------------------------------------------------------------


def test_run_returns_needs_revision_with_corrected_formula() -> None:
    payload = json.dumps(
        {
            "verdict": "needs_revision",
            "confidence": 0.85,
            "explanation": "Missing factor of 0.5.",
            "corrected_formula": "0.5 * m * v**2",
        }
    )
    agent = FormulaVerificationAgent(llm=_make_llm(payload))
    output = agent.run(
        FormulaVerificationInput(
            session_id="s1",
            problem="Kinetic energy",
            formula="m * v**2",
            variables={"m": 2.0, "v": 3.0},
        )
    )
    assert output.verdict == "needs_revision"
    assert output.corrected_formula == "0.5 * m * v**2"


# ---------------------------------------------------------------------------
# Fallback on parse failure
# ---------------------------------------------------------------------------


def test_run_returns_safe_default_on_invalid_json() -> None:
    agent = FormulaVerificationAgent(llm=_make_llm("not valid json {{{"))
    output = agent.run(
        FormulaVerificationInput(
            session_id="s1",
            problem="any",
            formula="x + 1",
            variables={"x": 1.0},
        )
    )
    assert output.verdict == "verified"
    assert output.confidence == pytest.approx(0.6)


def test_run_returns_safe_default_on_empty_response() -> None:
    agent = FormulaVerificationAgent(llm=_make_llm(""))
    output = agent.run(
        FormulaVerificationInput(
            session_id="s1",
            problem="any",
            formula="x",
            variables={"x": 1.0},
        )
    )
    assert output.verdict == "verified"


# ---------------------------------------------------------------------------
# Code block stripping
# ---------------------------------------------------------------------------


def test_run_strips_markdown_code_block() -> None:
    inner = json.dumps(
        {
            "verdict": "verified",
            "confidence": 0.9,
            "explanation": "OK",
            "corrected_formula": None,
        }
    )
    payload = f"```json\n{inner}\n```"
    agent = FormulaVerificationAgent(llm=_make_llm(payload))
    output = agent.run(
        FormulaVerificationInput(
            session_id="s1",
            problem="test",
            formula="x",
            variables={"x": 1.0},
        )
    )
    assert output.verdict == "verified"


# ---------------------------------------------------------------------------
# Context chunks included in prompt
# ---------------------------------------------------------------------------


def test_run_includes_context_chunks_in_prompt() -> None:
    """Verify that context chunks are embedded in the prompt passed to the LLM."""
    payload = json.dumps(
        {
            "verdict": "verified",
            "confidence": 0.95,
            "explanation": "Confirmed by document.",
            "corrected_formula": None,
        }
    )
    captured: list[AgentInput] = []

    class _CapturingLLM(BaseLLM):
        def generate(
            self,
            p: AgentInput,
            response_mode: Literal["chat", "tool_call", "json"] = "chat",
            tools: Optional[list[dict[str, Any]]] = None,
        ) -> AIResponse:
            captured.append(p)
            return AIResponse(type="text", content=payload)

    agent = FormulaVerificationAgent(llm=_CapturingLLM())
    chunks = [RetrievedChunk(chunk_id="c1", score=0.9, text="KE = 0.5mv^2", source="doc")]
    agent.run(
        FormulaVerificationInput(
            session_id="s1",
            problem="KE formula",
            formula="0.5 * m * v**2",
            variables={"m": 1.0, "v": 2.0},
            context_chunks=chunks,
        )
    )
    assert captured, "LLM was never called"
    user_message = captured[0].user_message
    assert "KE = 0.5mv^2" in user_message
    assert "RELEVANT CONTEXT FROM DOCUMENTS" in user_message


# ---------------------------------------------------------------------------
# Schema output model
# ---------------------------------------------------------------------------


def test_formula_verification_output_schema() -> None:
    out = FormulaVerificationOutput(
        verdict="verified",
        confidence=0.9,
        explanation="ok",
        corrected_formula=None,
    )
    assert out.verdict == "verified"
    assert out.corrected_formula is None


def test_formula_verification_output_invalid_confidence_raises() -> None:
    with pytest.raises(Exception):
        FormulaVerificationOutput(
            verdict="verified",
            confidence=1.5,  # > 1.0 — violates ge/le constraint
            explanation="",
        )


# ---------------------------------------------------------------------------
# Invalid verdict is coerced to "verified"
# ---------------------------------------------------------------------------


def test_run_invalid_verdict_coerced_to_verified() -> None:
    payload = json.dumps(
        {
            "verdict": "unknown_verdict",
            "confidence": 0.5,
            "explanation": "unexpected",
            "corrected_formula": None,
        }
    )
    agent = FormulaVerificationAgent(llm=_make_llm(payload))
    output = agent.run(
        FormulaVerificationInput(
            session_id="s1",
            problem="any",
            formula="x",
            variables={"x": 1.0},
        )
    )
    assert output.verdict == "verified"
