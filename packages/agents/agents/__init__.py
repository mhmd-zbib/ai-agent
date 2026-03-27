"""
agents — multi-agent orchestration package.

Provides BaseAgent, tool infrastructure, and specialized agent implementations
for orchestration, research, document processing, and extraction.
"""

from agents.core.base import BaseAgent
from agents.core.context import AgentContext, AgentResult

__all__ = [
    "AgentContext",
    "AgentResult",
    "BaseAgent",
]
