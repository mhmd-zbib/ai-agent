"""
agents.core.base — BaseAgent abstract base class.

All concrete agent implementations must subclass BaseAgent and implement run().
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from agents.core.context import AgentContext, AgentResult

__all__ = ["BaseAgent"]


class BaseAgent(ABC):
    """Abstract base for every agent in the agents package."""

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult:
        """
        Execute the agent given the provided context.

        Args:
            context: AgentContext carrying the user message, session, history,
                     and any domain-specific metadata.

        Returns:
            AgentResult with the agent's response content and metadata.
        """
        ...
