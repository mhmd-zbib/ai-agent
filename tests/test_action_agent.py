"""
Unit tests for ActionAgent.
"""

from __future__ import annotations


from app.modules.agent.schemas.sub_agents import ActionInput
from app.modules.agent.agents.action_agent import ActionAgent
from app.modules.tools.base import BaseTool
from app.modules.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echoes the 'value' argument."
    parameters = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    }

    def run(self, arguments: dict[str, object]) -> str:
        return str(arguments.get("value", ""))


class _CaptureTool(BaseTool):
    name = "capture"
    description = "Captures params."
    parameters = {"type": "object", "properties": {}}

    def __init__(self) -> None:
        self.received: dict[str, object] = {}

    def run(self, arguments: dict[str, object]) -> str:
        self.received = dict(arguments)
        return "captured"


class _FailingTool(BaseTool):
    name = "failing"
    description = "Always raises."
    parameters = {"type": "object", "properties": {}}

    def run(self, arguments: dict[str, object]) -> str:
        raise ValueError("intentional failure")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(*tools: BaseTool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def _make_agent(*tools: BaseTool) -> ActionAgent:
    return ActionAgent(tool_registry=_make_registry(*tools))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_executes_tool_successfully() -> None:
    agent = _make_agent(_EchoTool())
    output = agent.run(
        ActionInput(
            instruction="say hello",
            tool_id="echo",
            tool_params={"value": "hello"},
            session_id="s1",
        )
    )

    assert output.succeeded is True
    assert output.result == "hello"
    assert output.error_message == ""
    assert output.tool_id == "echo"


def test_unknown_tool_returns_not_registered_error() -> None:
    agent = _make_agent(_EchoTool())
    output = agent.run(
        ActionInput(instruction="run missing", tool_id="ghost", session_id="s1")
    )

    assert output.succeeded is False
    assert "not registered" in output.error_message
    assert "ghost" in output.error_message


def test_failing_tool_returns_error_output() -> None:
    agent = _make_agent(_FailingTool())
    output = agent.run(
        ActionInput(instruction="cause error", tool_id="failing", session_id="s1")
    )

    assert output.succeeded is False
    assert "failing" in output.error_message
    assert "raised" in output.error_message


def test_user_id_injected_into_params() -> None:
    capture = _CaptureTool()
    agent = _make_agent(capture)
    agent.run(
        ActionInput(
            instruction="capture",
            tool_id="capture",
            tool_params={},
            user_id="tenant-42",
            session_id="s1",
        )
    )

    assert capture.received.get("user_id") == "tenant-42"


def test_existing_params_preserved() -> None:
    capture = _CaptureTool()
    agent = _make_agent(capture)
    agent.run(
        ActionInput(
            instruction="capture",
            tool_id="capture",
            tool_params={"key": "val"},
            user_id="u1",
            session_id="s1",
        )
    )

    assert capture.received.get("key") == "val"
    assert capture.received.get("user_id") == "u1"


def test_empty_user_id_not_injected() -> None:
    capture = _CaptureTool()
    agent = _make_agent(capture)
    agent.run(
        ActionInput(
            instruction="capture",
            tool_id="capture",
            tool_params={},
            user_id="",
            session_id="s1",
        )
    )

    assert "user_id" not in capture.received


def test_list_tools_delegates_to_registry() -> None:
    agent = _make_agent(_EchoTool(), _FailingTool())
    tools = agent.list_tools()

    assert "echo" in tools
    assert "failing" in tools
    assert len(tools) == 2
