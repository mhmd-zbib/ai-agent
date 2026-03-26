from __future__ import annotations

from uuid import uuid4

from app.modules.agent.schemas.sub_agents import OrchestratorInput
from app.modules.agent.services.orchestrator_service import OrchestratorService
from app.modules.chat.schemas import (
    ChatRequest,
    ChatResponse,
    SessionCreateResponse,
    SessionResetResponse,
)
from app.shared.enums import University
from app.shared.logging import get_logger
from app.shared.protocols import IMemoryService
from app.shared.schemas import MemoryEntry, ResponseMetadata

logger = get_logger(__name__)


class ChatService:
    """
    Chat service that orchestrates session, memory persistence, and the multi-agent pipeline.

    Delegates all LLM invocation, retrieval, reasoning, and tool execution to OrchestratorService.
    """

    def __init__(
        self,
        orchestrator_service: OrchestratorService,
        memory_service: IMemoryService,
    ) -> None:
        self._orchestrator_service = orchestrator_service
        self._memory_service = memory_service

    def create_session(self, course_code: str = "") -> SessionCreateResponse:
        session_id = str(uuid4())
        # Store course_code in Redis as session metadata
        if course_code:
            self._memory_service.set_metadata(session_id, "course_code", course_code)
        # Prime cache path so first chat turn uses Redis-first flow consistently.
        self._memory_service.get_session_state(session_id)
        return SessionCreateResponse(session_id=session_id)

    def _persist_turn(
        self, session_id: str, user_message: str, assistant_message: str
    ) -> None:
        self._memory_service.append_message(
            session_id,
            MemoryEntry(role="user", content=user_message),
        )
        self._memory_service.append_message(
            session_id,
            MemoryEntry(role="assistant", content=assistant_message),
        )

    def reply(
        self,
        payload: ChatRequest,
        user_id: str = "",
        university_name: University = University.LIU,
    ) -> ChatResponse:
        session_id = payload.session_id
        state = self._memory_service.get_session_state(session_id)

        course_code = self._memory_service.get_metadata(session_id, "course_code")

        orch_input = OrchestratorInput(
            user_message=payload.question,
            session_id=session_id,
            history=[
                {"role": item.role, "content": item.content} for item in state.messages
            ],
            user_id=user_id,
            use_retrieval=payload.use_rag,
            course_code=course_code,
            university_name=str(university_name),
        )

        orch_output = self._orchestrator_service.run(orch_input)

        self._persist_turn(
            session_id=session_id,
            user_message=payload.question,
            assistant_message=orch_output.answer,
        )

        return ChatResponse(
            session_id=session_id,
            response_mode="chat",
            type="text",
            content=orch_output.answer,
            tool_action=None,
            metadata=ResponseMetadata(confidence=orch_output.confidence),
        )

    def reset_session(self, session_id: str) -> SessionResetResponse:
        self._memory_service.delete_metadata(session_id, "course_code")
        cleared = self._memory_service.clear_session(session_id)
        return SessionResetResponse(session_id=session_id, cleared=cleared)

    def close(self) -> None:
        self._memory_service.close()
