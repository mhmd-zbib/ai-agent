"""
Intra-module protocols (interfaces) for all sub-agents.

OrchestratorService depends on these, not on concrete implementations,
so sub-agents can be mocked, swapped, or extended without touching the orchestrator.
"""
from __future__ import annotations

from typing import Protocol

from app.modules.agent.schemas.sub_agents import (
    ActionInput,
    ActionOutput,
    CritiqueInput,
    CritiqueOutput,
    MemoryInput,
    MemoryOutput,
    ReasoningInput,
    ReasoningOutput,
    RetrievalInput,
    RetrievalOutput,
)

__all__ = [
    "IActionAgent",
    "ICritiqueAgent",
    "IMemoryAgent",
    "IReasoningAgent",
    "IRetrievalAgent",
]


class IRetrievalAgent(Protocol):
    def run(self, input: RetrievalInput) -> RetrievalOutput: ...


class IReasoningAgent(Protocol):
    def run(self, input: ReasoningInput) -> ReasoningOutput: ...


class ICritiqueAgent(Protocol):
    def run(self, input: CritiqueInput) -> CritiqueOutput: ...


class IMemoryAgent(Protocol):
    def run(self, input: MemoryInput) -> MemoryOutput: ...


class IActionAgent(Protocol):
    def run(self, input: ActionInput) -> ActionOutput: ...

    def list_tools(self) -> list[str]: ...
