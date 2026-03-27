"""
agents.core.context — re-exports AgentContext and AgentResult from shared.

These types are the canonical input/output contract for all agents.
"""

from shared.models.agent import AgentContext, AgentResult

__all__ = ["AgentContext", "AgentResult"]
