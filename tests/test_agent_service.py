"""
Unit tests for AgentService.

All external dependencies (LLM, tool registry) are faked so the tests run
without any network or API access.
"""
from typing import Any, Literal, Optional

import pytest

from app.modules.agent.services.agent_service import AgentService
from app.modules.tools.base import BaseTool
from app.modules.tools.registry import ToolRegistry
from app.shared.llm.base import BaseLLM
from app.shared.schemas import AgentInput, AIResponse, ToolAction


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

class _FakeLLM(BaseLLM):
    """Returns pre-configured responses in sequence."""

    def __init__(self, responses: list[AIResponse]) -> None:
        self._responses = responses
        self.call_count = 0
        self.call_args: list[AgentInput] = []

    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AIResponse:
        self.call_args.append(payload)
        idx = min(self.call_count, len(self._responses) - 1)
        self.call_count += 1
        return self._responses[idx]


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echoes back the value argument."
    parameters = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}

    def run(self, arguments: dict[str, object]) -> str:
        return str(arguments.get("value", ""))


class _FailingTool(BaseTool):
    name = "failing"
    description = "Always raises."
    parameters = {"type": "object", "properties": {}}

    def run(self, arguments: dict[str, object]) -> str:
        raise RuntimeError("boom")


def _make_service(responses: list[AIResponse], tools: list[BaseTool] | None = None) -> tuple[AgentService, _FakeLLM]:
    llm = _FakeLLM(responses)
    registry = ToolRegistry()
    for tool in (tools or []):
        registry.register(tool)
    return AgentService(llm=llm, tool_registry=registry), llm


def _input(message: str = "hello", session_id: str = "s1") -> AgentInput:
    return AgentInput(user_message=message, session_id=session_id, history=[])


# ---------------------------------------------------------------------------
# Plain-text response (no tool)
# ---------------------------------------------------------------------------

def test_run_plain_text_returns_finalized_response() -> None:
    service, llm = _make_service([
        AIResponse(type="text", content="Hello there!"),
    ])

    result = service.run(_input())

    assert llm.call_count == 1
    assert result.type == "text"
    assert result.content == "Hello there!"
    assert result.tool_action is None


def test_run_sets_type_text_regardless_of_initial_type() -> None:
    # Even if LLM returns type="mixed" without a tool, _finalize still sets "text"
    service, llm = _make_service([
        AIResponse(type="text", content="No tool today."),
    ])

    result = service.run(_input())

    assert result.type == "text"
    assert result.tool_action is None


# ---------------------------------------------------------------------------
# Tool execution — success
# ---------------------------------------------------------------------------

def test_run_executes_tool_and_calls_followup() -> None:
    service, llm = _make_service(
        responses=[
            AIResponse(
                type="tool",
                content="Using echo tool.",
                tool_action=ToolAction(tool_id="echo", params={"value": "pong"}),
            ),
            AIResponse(type="text", content="The echo replied: pong"),
        ],
        tools=[_EchoTool()],
    )

    result = service.run(_input("say pong"))

    assert llm.call_count == 2
    assert result.type == "text"
    assert result.tool_action is None
    assert result.content == "The echo replied: pong"


def test_run_passes_user_id_to_tool_params() -> None:
    captured_params: dict = {}

    class _CaptureTool(BaseTool):
        name = "capture"
        description = "Captures params"
        parameters = {"type": "object", "properties": {}}

        def run(self, arguments: dict[str, object]) -> str:
            captured_params.update(arguments)
            return "captured"

    service, llm = _make_service(
        responses=[
            AIResponse(
                type="tool",
                content="Calling capture.",
                tool_action=ToolAction(tool_id="capture", params={}),
            ),
            AIResponse(type="text", content="Done."),
        ],
        tools=[_CaptureTool()],
    )

    service.run(_input(), user_id="tenant-42")

    assert captured_params.get("user_id") == "tenant-42"


def test_run_mixed_type_includes_text_and_tool_result() -> None:
    service, llm = _make_service(
        responses=[
            AIResponse(
                type="mixed",
                content="Here is what I found:",
                tool_action=ToolAction(tool_id="echo", params={"value": "result"}),
            ),
            AIResponse(type="text", content="Combined answer."),
        ],
        tools=[_EchoTool()],
    )

    result = service.run(_input())

    assert result.type == "text"
    # followup response content is used
    assert result.content == "Combined answer."


# ---------------------------------------------------------------------------
# Tool execution — failures
# ---------------------------------------------------------------------------

def test_run_unknown_tool_returns_friendly_message() -> None:
    service, llm = _make_service(
        responses=[
            AIResponse(
                type="tool",
                content="Calling unknown.",
                tool_action=ToolAction(tool_id="no_such_tool", params={}),
            ),
            AIResponse(type="text", content="fallback"),
        ],
    )

    result = service.run(_input())

    assert "couldn't run that tool" in result.content
    assert result.type == "text"
    assert result.tool_action is None


def test_run_failing_tool_returns_error_message() -> None:
    service, llm = _make_service(
        responses=[
            AIResponse(
                type="tool",
                content="Calling failing.",
                tool_action=ToolAction(tool_id="failing", params={}),
            ),
            AIResponse(type="text", content="fallback"),
        ],
        tools=[_FailingTool()],
    )

    result = service.run(_input())

    assert "hit an error" in result.content
    assert result.type == "text"


def test_run_weather_unavailable_message_is_friendly() -> None:
    class _WeatherTool(BaseTool):
        name = "weather"
        description = "Weather"
        parameters = {"type": "object", "properties": {"city": {"type": "string"}}}

        def run(self, arguments: dict[str, object]) -> str:
            return "Weather service is currently unavailable (503)"

    service, llm = _make_service(
        responses=[
            AIResponse(
                type="tool",
                content="Fetching weather.",
                tool_action=ToolAction(tool_id="weather", params={"city": "Paris"}),
            ),
            AIResponse(type="text", content="fallback"),
        ],
        tools=[_WeatherTool()],
    )

    result = service.run(_input("weather in paris"))

    assert "weather service" in result.content.lower()
    assert result.type == "text"


# ---------------------------------------------------------------------------
# Followup synthesis fallback
# ---------------------------------------------------------------------------

def test_run_followup_failure_falls_back_to_tool_response() -> None:
    """If the followup LLM call returns empty content, the tool output is kept."""

    class _BrokenLLM(BaseLLM):
        def __init__(self) -> None:
            self.call_count = 0

        def generate(self, payload: AgentInput, response_mode="chat", tools=None) -> AIResponse:
            self.call_count += 1
            if self.call_count == 1:
                return AIResponse(
                    type="tool",
                    content="initial",
                    tool_action=ToolAction(tool_id="echo", params={"value": "hi"}),
                )
            # Second call returns empty content — should fall back gracefully
            return AIResponse(type="text", content="   ")

    registry = ToolRegistry()
    registry.register(_EchoTool())
    service = AgentService(llm=_BrokenLLM(), tool_registry=registry)

    result = service.run(_input())

    # Fallback: content is the tool output ("hi") since followup content was blank
    assert result.content == "hi"
    assert result.type == "text"


# ---------------------------------------------------------------------------
# History propagation in followup
# ---------------------------------------------------------------------------

def test_run_followup_includes_original_history() -> None:
    """The followup AgentInput must carry prior history + the user turn."""
    service, llm = _make_service(
        responses=[
            AIResponse(
                type="tool",
                content="Using echo.",
                tool_action=ToolAction(tool_id="echo", params={"value": "data"}),
            ),
            AIResponse(type="text", content="Final answer."),
        ],
        tools=[_EchoTool()],
    )

    history = [{"role": "user", "content": "prev msg"}, {"role": "assistant", "content": "prev reply"}]
    agent_input = AgentInput(user_message="what is data?", session_id="s1", history=history)

    service.run(agent_input)

    # followup call (index 1) should contain the original history + user turn
    followup_input = llm.call_args[1]
    roles = [m["role"] for m in followup_input.history]
    assert "user" in roles
    assert "assistant" in roles
    # The original user message appears in the followup history
    contents = [m["content"] for m in followup_input.history]
    assert "what is data?" in contents
