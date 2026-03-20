from typing import Any, Literal, Optional

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput, ToolCall
from app.modules.agent.services.tool_executor import ToolExecutor
from app.modules.tools.base import BaseTool
from app.modules.tools.registry import ToolRegistry
from app.shared.schemas import AIResponse, ToolAction


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echo back"
    parameters = {"type": "object", "properties": {"value": {"type": "string"}}}

    def run(self, arguments: dict[str, object]) -> str:
        return str(arguments.get("value", ""))


class _FailingTool(BaseTool):
    name = "failing"
    description = "Always fails"
    parameters = {"type": "object", "properties": {}}

    def run(self, arguments: dict[str, object]) -> str:  # noqa: ARG002
        raise RuntimeError("boom")


class _FakeLLM(BaseLLM):
    def __init__(self, response: AIResponse) -> None:
        self._response = response

    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AIResponse:  # noqa: ARG002
        return self._response


def test_tool_registry_duplicate_registration_rejected() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool())

    try:
        registry.register(_EchoTool())
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("Expected duplicate registration to raise ValueError")


def test_tool_registry_list_tools_exposes_registered_names() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool())

    assert registry.list_tools() == ["echo"]


def test_tool_executor_returns_error_for_missing_tool() -> None:
    registry = ToolRegistry()
    executor = ToolExecutor(registry)

    result = executor.run([ToolCall(name="missing", arguments={})])[0]

    assert result.name == "missing"
    assert result.output == "Error: Tool 'missing' not found"


def test_tool_executor_returns_sanitized_error_for_failing_tool() -> None:
    registry = ToolRegistry()
    registry.register(_FailingTool())
    executor = ToolExecutor(registry)

    result = executor.run([ToolCall(name="failing", arguments={})])[0]

    assert result.name == "failing"
    assert result.output == "Error: Tool execution failed"
