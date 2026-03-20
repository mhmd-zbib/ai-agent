from app.modules.chat.schemas import ChatRequest
from app.modules.chat.services.chat_service import ChatService
from app.modules.memory.schemas import SessionState
from app.modules.tools.base import BaseTool
from app.modules.tools.registry import ToolRegistry
from app.shared.schemas import AIResponse, ToolAction


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


class _FakeLLM:
    def __init__(self, response: AIResponse) -> None:
        self._response = response

    def generate(self, payload, response_mode="chat", tools=None):
        return self._response


def test_chat_service_tool_type_returns_clean_tool_content() -> None:
    registry = ToolRegistry()
    registry.register(_FakeTool())
    memory_service = _FakeMemoryService()

    llm_response = AIResponse(
        type="tool",
        content="Calling tool: weather",
        tool_action=ToolAction(tool_id="weather", params={"city": "Paris"}),
    )
    service = ChatService(llm=_FakeLLM(llm_response), memory_service=memory_service, tool_registry=registry)

    response = service.reply(ChatRequest(session_id="s1", message="weather in paris"))

    assert "Calling tool" not in response.content
    assert "Tool Result:" not in response.content
    assert response.content == "Current weather in Paris, France: Clear sky. Temperature: 15.3C."


def test_chat_service_mixed_type_keeps_text_without_wrapper_label() -> None:
    registry = ToolRegistry()
    registry.register(_FakeTool())
    memory_service = _FakeMemoryService()

    llm_response = AIResponse(
        type="mixed",
        content="Here is the weather update:",
        tool_action=ToolAction(tool_id="weather", params={"city": "Paris"}),
    )
    service = ChatService(llm=_FakeLLM(llm_response), memory_service=memory_service, tool_registry=registry)

    response = service.reply(ChatRequest(session_id="s1", message="weather in paris"))

    assert "Tool Result:" not in response.content
    assert response.content.startswith("Here is the weather update:")
    assert "Current weather in Paris, France: Clear sky." in response.content

