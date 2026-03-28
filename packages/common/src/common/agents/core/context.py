"""agents.core.context — AgentContext and AgentResult data classes."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentContext:
    """Encapsulates everything an agent needs to process a request."""

    user_message: str
    session_id: str
    user_id: str
    history: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Encapsulates the output of an agent run."""

    content: str
    response_type: str = "text"
    metadata: dict[str, object] = field(default_factory=dict)
