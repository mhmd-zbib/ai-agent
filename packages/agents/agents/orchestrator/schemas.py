"""
agents.orchestrator.schemas — Pydantic input/output models for all sub-agents
and the orchestrator.

Merged from:
  packages/api/src/api/modules/agent/schemas/sub_agents.py
  packages/api/src/api/modules/agent/schemas/output.py
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

__all__ = [
    "ActionInput",
    "ActionOutput",
    "AgentOutput",
    "AgentStep",
    "ClaimVerification",
    "CritiqueInput",
    "CritiqueOutput",
    "ExtractedFact",
    "FormulaVerificationInput",
    "FormulaVerificationOutput",
    "MemoryInput",
    "MemoryOutput",
    "OrchestratorInput",
    "OrchestratorOutput",
    "OrchestratorPlan",
    "ReasoningInput",
    "ReasoningOutput",
    "ReasoningStep",
    "RetrievalInput",
    "RetrievalOutput",
    "RetrievedChunk",
    "ToolCall",
    "ToolResult",
]

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class RetrievedChunk(BaseModel):
    chunk_id: str
    score: float
    text: str
    source: str = ""


# ---------------------------------------------------------------------------
# RetrievalAgent I/O
# ---------------------------------------------------------------------------


class RetrievalInput(BaseModel):
    query: str
    user_id: str = ""
    top_k: int = 5
    filters: dict[str, str] = Field(default_factory=dict)
    strategy: Literal["vector", "keyword", "hybrid"] = "vector"
    course_code: str = ""
    university_name: str = ""


class RetrievalOutput(BaseModel):
    chunks: list[RetrievedChunk]
    strategy_used: Literal["vector", "keyword", "hybrid"]
    query_used: str


# ---------------------------------------------------------------------------
# ReasoningAgent I/O
# ---------------------------------------------------------------------------


class ReasoningInput(BaseModel):
    question: str
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    session_id: str = ""
    history: list[dict[str, str]] = Field(default_factory=list)


class ReasoningStep(BaseModel):
    step_number: int
    reasoning: str


class ReasoningOutput(BaseModel):
    answer: str
    steps: list[ReasoningStep] = Field(default_factory=list)
    context_adequacy: Literal["sufficient", "insufficient"] = "sufficient"
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# CritiqueAgent I/O
# ---------------------------------------------------------------------------


class CritiqueInput(BaseModel):
    question: str
    draft_answer: str
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    session_id: str = ""


class ClaimVerification(BaseModel):
    claim: str
    supported: bool
    source_chunk_id: str | None = None
    note: str = ""


class CritiqueOutput(BaseModel):
    verdict: Literal["approved", "needs_revision"]
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    verifications: list[ClaimVerification] = Field(default_factory=list)
    revision_instructions: str = ""


# ---------------------------------------------------------------------------
# MemoryAgent I/O
# ---------------------------------------------------------------------------


class MemoryInput(BaseModel):
    session_id: str
    conversation_summary: str


class ExtractedFact(BaseModel):
    category: Literal["decision", "topic", "preference", "open_question", "other"]
    fact: str
    importance: Literal["high", "medium", "low"]


class MemoryOutput(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)
    summary_for_storage: str = ""


# ---------------------------------------------------------------------------
# ActionAgent I/O
# ---------------------------------------------------------------------------


class ActionInput(BaseModel):
    instruction: str
    tool_id: str
    tool_params: dict[str, object] = Field(default_factory=dict)
    user_id: str = ""
    session_id: str = ""


class ActionOutput(BaseModel):
    tool_id: str
    result: str
    succeeded: bool
    error_message: str = ""


# ---------------------------------------------------------------------------
# FormulaVerificationAgent I/O
# ---------------------------------------------------------------------------


class FormulaVerificationInput(BaseModel):
    session_id: str = ""
    problem: str
    formula: str
    variables: dict[str, float] = Field(default_factory=dict)
    context_chunks: list[RetrievedChunk] = Field(default_factory=list)


class FormulaVerificationOutput(BaseModel):
    verdict: Literal["verified", "needs_revision"]
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    explanation: str = ""
    corrected_formula: str | None = None


# ---------------------------------------------------------------------------
# Orchestrator I/O
# ---------------------------------------------------------------------------


class AgentStep(BaseModel):
    agent: Literal[
        "retrieval_agent",
        "reasoning_agent",
        "critique_agent",
        "memory_agent",
        "action_agent",
        "formula_verification_agent",
    ]
    rationale: str
    inputs: dict[str, object] = Field(default_factory=dict)


class OrchestratorPlan(BaseModel):
    """Internal only — not returned to callers."""

    steps: list[AgentStep]
    final_synthesis_note: str = ""


class OrchestratorInput(BaseModel):
    user_message: str
    session_id: str
    history: list[dict[str, str]] = Field(default_factory=list)
    user_id: str = ""
    use_retrieval: bool = False
    course_code: str = ""
    university_name: str = ""


class OrchestratorOutput(BaseModel):
    answer: str
    session_id: str
    agent_trace: list[dict[str, object]] = Field(default_factory=list)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Agent output schemas (from agent/schemas/output.py)
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    name: str
    output: str


class AgentOutput(BaseModel):
    message: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
