"""agents.core.base — BaseAgent abstract class."""
from __future__ import annotations

from abc import ABC, abstractmethod

from common.agents.core.context import AgentContext, AgentResult


class BaseAgent(ABC):
    """Abstract base for all agent implementations."""

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult:
        """Execute the agent and return a result."""
