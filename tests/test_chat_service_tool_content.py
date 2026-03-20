from app.modules.chat.schemas import ChatRequest
from app.modules.chat.services.chat_service import ChatService
from app.modules.memory.schemas import SessionState
from app.modules.tools.base import BaseTool
from app.modules.tools.registry import ToolRegistry
from app.shared.schemas import AIResponse, ToolAction
from typing import Any, Literal, Optional

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput


class _FakeMemoryService:
    def __init__(self) -> None:
        self.messages = []

    def get_session_state(self, session_id: str) -> SessionState:
        return SessionState(session_id=session_id, messages=[])

    def append_message(self, session_id: str, entry) -> None:
        self.messages.append((session_id, entry))

    def clear_session(self, session_id: str) -> bool:
        return True

    def close(self) -> None:
        return None


class _FakeTool(BaseTool):
    name = "weather"
    description = "Fake weather"
    parameters = {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}

    def run(self, arguments: dict[str, object]) -> str:
        return "Current weather in Paris, France: Clear sky. Temperature: 15.3C."


class _FakeLLM(BaseLLM):
    def __init__(self, responses: list[AIResponse]) -> None:
        self._responses = responses
        self.call_count = 0

    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AIResponse:  # noqa: ARG002
        idx = min(self.call_count, len(self._responses) - 1)
        self.call_count += 1
        return self._responses[idx]


def test_chat_service_tool_type_returns_clean_tool_content() -> None:
    registry = ToolRegistry()
    registry.register(_FakeTool())
    memory_service = _FakeMemoryService()

    llm = _FakeLLM(
        responses=[
            AIResponse(
                type="tool",
                content="Calling tool: weather",
                tool_action=ToolAction(tool_id="weather", params={"city": "Paris"}),
            ),
            AIResponse(
                type="text",
                content="The weather in Paris is clear, around 15C. Great for a walk.",
                tool_action=None,
            ),
        ]
    )
    service = ChatService(llm=llm, memory_service=memory_service, tool_registry=registry)

    response = service.reply(ChatRequest(session_id="s1", message="weather in paris"))

    assert llm.call_count == 2
    assert response.type == "text"
    assert response.tool_action is None
    assert response.content == "The weather in Paris is clear, around 15C. Great for a walk."


def test_chat_service_mixed_type_keeps_text_without_wrapper_label() -> None:
    registry = ToolRegistry()
    registry.register(_FakeTool())
    memory_service = _FakeMemoryService()

    llm = _FakeLLM(
        responses=[
            AIResponse(
                type="mixed",
                content="Here is the weather update:",
                tool_action=ToolAction(tool_id="weather", params={"city": "Paris"}),
            ),
            AIResponse(
                type="text",
                content="It's cool and clear in Paris today, so it is generally fine for a short trip.",
                tool_action=None,
            ),
        ]
    )
    service = ChatService(llm=llm, memory_service=memory_service, tool_registry=registry)

    response = service.reply(ChatRequest(session_id="s1", message="weather in paris"))

    assert llm.call_count == 2
    assert response.type == "text"
    assert response.tool_action is None
    assert "Tool Result:" not in response.content
    assert "trip" in response.content.lower()
