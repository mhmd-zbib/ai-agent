"""
runner — top-level agent dispatcher.

Routes AgentContext to the appropriate agent implementation.
For now all requests are routed to OrchestratorAgent.
"""

from __future__ import annotations

from agents.core.context import AgentContext, AgentResult
from agents.orchestrator.agent import OrchestratorAgent

__all__ = ["run_agent"]


async def run_agent(name: str, context: AgentContext, agent: OrchestratorAgent) -> AgentResult:
    """
    Dispatch a named agent request.

    Args:
        name: Logical agent name (currently unused; reserved for future routing).
        context: The AgentContext containing user message, session, history, etc.
        agent: A pre-wired OrchestratorAgent instance (injected by the caller).

    Returns:
        AgentResult with the synthesized answer and metadata.
    """
    return await agent.run(context)
