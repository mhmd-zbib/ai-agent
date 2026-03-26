"""Shared test fixtures."""

import pytest

from app.shared.config import AgentConfig


@pytest.fixture
def agent_config() -> AgentConfig:
    """Default agent configuration for tests."""
    return AgentConfig()
