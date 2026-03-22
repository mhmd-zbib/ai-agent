"""
Unit tests for OrchestratorService.

All sub-agents and the LLM are faked.
"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

import pytest

from app.modules.agent.schemas.sub_agents import (
    ActionInput,
    ActionOutput,
    CritiqueInput,
    CritiqueOutput,
    MemoryInput,
    MemoryOutput,
    OrchestratorInput,
    ReasoningInput,
    ReasoningOutput,
    RetrievalInput,
    RetrievalOutput,
    RetrievedChunk,
)
from app.modules.agent.agents.action_agent import ActionAgent
from app.modules.agent.agents.critique_agent import CritiqueAgent
from app.modules.agent.agents.memory_agent import MemoryAgent
from app.modules.agent.agents.reasoning_agent import ReasoningAgent
from app.modules.agent.agents.retrieval_agent import RetrievalAgent
from app.modules.agent.services.orchestrator_service import OrchestratorService
from app.modules.tools.base import BaseTool
from app.modules.tools.registry import ToolRegistry
from app.shared.llm.base import BaseLLM
from app.shared.schemas import AgentInput, AIResponse


# ---------------------------------------------------------------------------
# Fake LLM (returns pre-configured strings in sequence)
# ---------------------------------------------------------------------------


class _FakeLLM(BaseLLM):
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.call_count = 0
        self.prompts: list[str] = []

    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AIResponse:
        self.prompts.append(payload.user_message)
        idx = min(self.call_count, len(self._responses) - 1)
        self.call_count += 1
        return AIResponse(type="text", content=self._responses[idx])


# ---------------------------------------------------------------------------
# Fake sub-agents (bypass real LLM/vector calls)
# ---------------------------------------------------------------------------


class _FakeRetrievalAgent:
    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self._chunks = chunks or []
        self.called = False

    def run(self, input: RetrievalInput) -> RetrievalOutput:
        self.called = True
        return RetrievalOutput(chunks=self._chunks, strategy_used="vector", query_used=input.query)


class _FakeReasoningAgent:
    def __init__(self, answer: str = "Reasoned answer.", confidence: float = 0.9) -> None:
        self._answer = answer
        self._confidence = confidence
        self.called = False
        self.last_input: ReasoningInput | None = None

    def run(self, input: ReasoningInput) -> ReasoningOutput:
        self.called = True
        self.last_input = input
        return ReasoningOutput(
            answer=self._answer, steps=[], context_adequacy="sufficient", confidence=self._confidence
        )


class _FakeCritiqueAgent:
    def __init__(self, verdict: str = "approved") -> None:
        self._verdict = verdict
        self.called = False

    def run(self, input: CritiqueInput) -> CritiqueOutput:
        self.called = True
        return CritiqueOutput(
            verdict=self._verdict,  # type: ignore[arg-type]
            confidence=0.9,
            verifications=[],
            revision_instructions="Fix it." if self._verdict == "needs_revision" else "",
        )


class _FakeMemoryAgent:
    def __init__(self) -> None:
        self.called = False

    def run(self, input: MemoryInput) -> MemoryOutput:
        self.called = True
        return MemoryOutput(facts=[], summary_for_storage="summary")


class _FakeActionAgent:
    def __init__(self, result: str = "42", succeeded: bool = True) -> None:
        self._result = result
        self._succeeded = succeeded
        self.called = False

    def list_tools(self) -> list[str]:
        return ["calculator"]

    def run(self, input: ActionInput) -> ActionOutput:
        self.called = True
        return ActionOutput(
            tool_id=input.tool_id,
            result=self._result,
            succeeded=self._succeeded,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan_json(*agent_names: str) -> str:
    steps = [{"agent": name, "rationale": f"use {name}", "inputs": {}} for name in agent_names]
    return json.dumps({"steps": steps, "final_synthesis_note": ""})


def _make_orchestrator(
    plan_responses: list[str],
    synthesis_response: str = "Final answer.",
    retrieval_agent: _FakeRetrievalAgent | None = None,
    reasoning_agent: _FakeReasoningAgent | None = None,
    critique_agent: _FakeCritiqueAgent | None = None,
    memory_agent: _FakeMemoryAgent | None = None,
    action_agent: _FakeActionAgent | None = None,
) -> tuple[OrchestratorService, _FakeLLM]:
    llm = _FakeLLM(plan_responses + [synthesis_response])
    service = OrchestratorService(
        llm=llm,
        retrieval_agent=retrieval_agent or _FakeRetrievalAgent(),  # type: ignore[arg-type]
        reasoning_agent=reasoning_agent or _FakeReasoningAgent(),  # type: ignore[arg-type]
        critique_agent=critique_agent or _FakeCritiqueAgent(),  # type: ignore[arg-type]
        memory_agent=memory_agent or _FakeMemoryAgent(),  # type: ignore[arg-type]
        action_agent=action_agent or _FakeActionAgent(),  # type: ignore[arg-type]
    )
    return service, llm


def _input(message: str = "hello", session_id: str = "s1") -> OrchestratorInput:
    return OrchestratorInput(user_message=message, session_id=session_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_reasoning_only_plan() -> None:
    reasoning = _FakeReasoningAgent(answer="Reasoned answer.")
    service, llm = _make_orchestrator(
        plan_responses=[_make_plan_json("reasoning_agent")],
        synthesis_response="Final synthesized answer.",
        reasoning_agent=reasoning,
    )

    output = service.run(_input())

    assert reasoning.called
    assert output.answer == "Final synthesized answer."
    assert output.session_id == "s1"
    # LLM called twice: planning + synthesis
    assert llm.call_count == 2


def test_retrieval_reasoning_critique_chain() -> None:
    chunks = [RetrievedChunk(chunk_id="c1", score=0.9, text="Context text")]
    retrieval = _FakeRetrievalAgent(chunks=chunks)
    reasoning = _FakeReasoningAgent(answer="Draft answer")
    critique = _FakeCritiqueAgent(verdict="approved")

    service, _ = _make_orchestrator(
        plan_responses=[_make_plan_json("retrieval_agent", "reasoning_agent", "critique_agent")],
        retrieval_agent=retrieval,
        reasoning_agent=reasoning,
        critique_agent=critique,
    )

    output = service.run(_input("document question"))

    assert retrieval.called
    assert reasoning.called
    assert critique.called
    # Chunks from retrieval should be passed to reasoning
    assert reasoning.last_input is not None
    assert len(reasoning.last_input.chunks) == 1
    assert reasoning.last_input.chunks[0].chunk_id == "c1"


def test_action_plan() -> None:
    action = _FakeActionAgent(result="Weather: sunny 25C", succeeded=True)
    service, _ = _make_orchestrator(
        plan_responses=[
            json.dumps(
                {
                    "steps": [{"agent": "action_agent", "rationale": "tool call", "inputs": {"tool_id": "weather"}}],
                    "final_synthesis_note": "",
                }
            )
        ],
        synthesis_response="It is sunny and 25 degrees Celsius.",
        action_agent=action,
    )

    output = service.run(_input("weather today"))

    assert action.called
    assert output.answer == "It is sunny and 25 degrees Celsius."


def test_fallback_on_bad_planning_json() -> None:
    """When planning LLM returns invalid JSON, service falls back to reasoning_agent."""
    reasoning = _FakeReasoningAgent(answer="Fallback reasoning.")
    service, _ = _make_orchestrator(
        plan_responses=["NOT VALID JSON AT ALL"],
        reasoning_agent=reasoning,
    )

    output = service.run(_input("anything"))

    assert reasoning.called
    assert output.answer != ""


def test_critique_skipped_if_no_reasoning_output() -> None:
    """If reasoning_agent is absent from plan and critique_agent is present, it is skipped."""
    critique = _FakeCritiqueAgent(verdict="needs_revision")
    service, _ = _make_orchestrator(
        # Plan only has critique (no reasoning first — guard should fire)
        plan_responses=[_make_plan_json("critique_agent")],
        critique_agent=critique,
    )

    output = service.run(_input("question without reasoning"))

    # critique skipped — no crash, trace shows skipped
    assert not critique.called
    skipped = [t for t in output.agent_trace if t.get("agent") == "critique_agent"]
    assert len(skipped) == 1
    assert skipped[0].get("skipped") is True


def test_correct_session_id_in_output() -> None:
    service, _ = _make_orchestrator(
        plan_responses=[_make_plan_json("reasoning_agent")],
    )
    output = service.run(_input(session_id="session-xyz"))

    assert output.session_id == "session-xyz"


def test_agent_trace_populated() -> None:
    service, _ = _make_orchestrator(
        plan_responses=[_make_plan_json("reasoning_agent")],
    )
    output = service.run(_input())

    trace_agents = [t["agent"] for t in output.agent_trace]
    assert "reasoning_agent" in trace_agents


def test_confidence_taken_from_reasoning_output() -> None:
    reasoning = _FakeReasoningAgent(answer="Precise answer.", confidence=0.77)
    service, _ = _make_orchestrator(
        plan_responses=[_make_plan_json("reasoning_agent")],
        reasoning_agent=reasoning,
    )

    output = service.run(_input())

    assert output.confidence == 0.77


def test_needs_revision_synthesis_includes_revision_instructions() -> None:
    """When critique returns needs_revision, synthesis prompt should include revision instructions."""
    reasoning = _FakeReasoningAgent(answer="Wrong draft.")
    critique = _FakeCritiqueAgent(verdict="needs_revision")
    llm = _FakeLLM(
        [_make_plan_json("reasoning_agent", "critique_agent"), "Revised final answer."]
    )
    service = OrchestratorService(
        llm=llm,
        retrieval_agent=_FakeRetrievalAgent(),  # type: ignore[arg-type]
        reasoning_agent=reasoning,  # type: ignore[arg-type]
        critique_agent=critique,  # type: ignore[arg-type]
        memory_agent=_FakeMemoryAgent(),  # type: ignore[arg-type]
        action_agent=_FakeActionAgent(),  # type: ignore[arg-type]
    )

    output = service.run(_input("question"))

    # Synthesis prompt should mention revision instructions
    synthesis_prompt = llm.prompts[-1]
    assert "revision" in synthesis_prompt.lower() or "Fix it." in synthesis_prompt
    assert output.answer == "Revised final answer."
