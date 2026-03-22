"""
Pydantic input/output models for all sub-agents and the orchestrator.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
# Orchestrator I/O
# ---------------------------------------------------------------------------


class AgentStep(BaseModel):
    agent: Literal[
        "retrieval_agent",
        "reasoning_agent",
        "critique_agent",
        "memory_agent",
        "action_agent",
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


class OrchestratorOutput(BaseModel):
    answer: str
    session_id: str
    agent_trace: list[dict[str, object]] = Field(default_factory=list)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


__all__ = [
    "ActionInput",
    "ActionOutput",
    "AgentStep",
    "ClaimVerification",
    "CritiqueInput",
    "CritiqueOutput",
    "ExtractedFact",
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
]
