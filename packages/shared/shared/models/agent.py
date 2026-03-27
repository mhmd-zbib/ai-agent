"""Agent context and result models shared across agents/ and api/ packages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentContext:
    """Input context passed to every agent invocation."""

    user_message: str
    session_id: str
    user_id: str
    history: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentResult:
    """Structured result returned by every agent."""

    content: str
    response_type: str  # "text" | "tool" | "mixed"
    tool_id: str | None = None
    tool_params: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
