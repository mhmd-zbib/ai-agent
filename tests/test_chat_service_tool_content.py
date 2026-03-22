"""
Unit tests for ChatService delegating to OrchestratorService.

Verifies that ChatService maps OrchestratorOutput to a correct ChatResponse.
"""
from __future__ import annotations

from app.modules.agent.schemas.sub_agents import OrchestratorInput, OrchestratorOutput
from app.modules.agent.services.orchestrator_service import OrchestratorService
from app.modules.chat.schemas import ChatRequest
from app.modules.chat.services.chat_service import ChatService
from app.modules.memory.schemas import SessionState


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeMemoryService:
    def __init__(self) -> None:
        self.messages: list[tuple[str, object]] = []

    def get_session_state(self, session_id: str) -> SessionState:
        return SessionState(session_id=session_id, messages=[])

    def append_message(self, session_id: str, entry: object) -> None:
        self.messages.append((session_id, entry))

    def clear_session(self, session_id: str) -> bool:
        return True

    def close(self) -> None:
        return None


class _FakeOrchestratorService:
    """Returns a configurable OrchestratorOutput for all run() calls."""

    def __init__(self, answer: str = "test answer", confidence: float = 0.9) -> None:
        self._answer = answer
        self._confidence = confidence
        self.call_count = 0
        self.last_input: OrchestratorInput | None = None

    def run(self, input: OrchestratorInput) -> OrchestratorOutput:
        self.call_count += 1
        self.last_input = input
        return OrchestratorOutput(
            answer=self._answer,
            session_id=input.session_id,
            agent_trace=[],
            confidence=self._confidence,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_chat_service_returns_text_type_with_orchestrator_answer() -> None:
    orchestrator = _FakeOrchestratorService(answer="The weather is clear.")
    service = ChatService(
        orchestrator_service=orchestrator,  # type: ignore[arg-type]
        memory_service=_FakeMemoryService(),
    )

    response = service.reply(ChatRequest(session_id="s1", message="weather today"))

    assert response.type == "text"
    assert response.content == "The weather is clear."
    assert response.tool_action is None
    assert response.session_id == "s1"


def test_chat_service_tool_action_always_none() -> None:
    """ChatService never exposes tool_action — the orchestrator handles tools internally."""
    orchestrator = _FakeOrchestratorService(answer="Done.")
    service = ChatService(
        orchestrator_service=orchestrator,  # type: ignore[arg-type]
        memory_service=_FakeMemoryService(),
    )

    response = service.reply(ChatRequest(session_id="s1", message="do something"))

    assert response.tool_action is None


def test_chat_service_passes_use_rag_flag() -> None:
    orchestrator = _FakeOrchestratorService(answer="Context-based answer.")
    service = ChatService(
        orchestrator_service=orchestrator,  # type: ignore[arg-type]
        memory_service=_FakeMemoryService(),
    )

    service.reply(ChatRequest(session_id="s1", message="document question", use_rag=True))

    assert orchestrator.last_input is not None
    assert orchestrator.last_input.use_retrieval is True


def test_chat_service_persists_turn() -> None:
    memory = _FakeMemoryService()
    orchestrator = _FakeOrchestratorService(answer="AI reply.")
    service = ChatService(
        orchestrator_service=orchestrator,  # type: ignore[arg-type]
        memory_service=memory,
    )

    service.reply(ChatRequest(session_id="s1", message="user msg"))

    # get_session_state + 2 appends (user + assistant)
    assert len(memory.messages) == 2
    roles = [entry.role for _, entry in memory.messages]  # type: ignore[union-attr]
    assert roles == ["user", "assistant"]


def test_chat_service_metadata_carries_confidence() -> None:
    orchestrator = _FakeOrchestratorService(answer="precise", confidence=0.77)
    service = ChatService(
        orchestrator_service=orchestrator,  # type: ignore[arg-type]
        memory_service=_FakeMemoryService(),
    )

    response = service.reply(ChatRequest(session_id="s1", message="q"))

    assert response.metadata is not None
    assert response.metadata.confidence == 0.77
