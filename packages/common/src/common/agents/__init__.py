"""
agents — multi-agent orchestration package.

Provides specialized agent implementations for orchestration, research,
document processing, and extraction.
"""

from .orchestrator.agent import OrchestratorAgent

__all__ = [
    "OrchestratorAgent",
]
