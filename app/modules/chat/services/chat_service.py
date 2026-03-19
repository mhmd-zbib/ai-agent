from uuid import uuid4

from app.modules.agent.schemas import AgentInput
from app.modules.agent.services.agent_service import AgentService
from app.modules.chat.schemas import ChatHistoryItem, ChatRequest, ChatResponse, SessionResetResponse
from app.modules.memory.schemas import MemoryEntry
from app.modules.memory.services.memory_service import MemoryService


class ChatService:
    def __init__(self, agent_service: AgentService, memory_service: MemoryService) -> None:
        self._agent_service = agent_service
        self._memory_service = memory_service

    def reply(self, payload: ChatRequest) -> ChatResponse:
        session_id = payload.session_id or str(uuid4())
        state = self._memory_service.get_session_state(session_id)

        agent_input = AgentInput(
            user_message=payload.message,
            session_id=session_id,
            history=[{"role": item.role, "content": item.content} for item in state.messages],
        )
        agent_output = self._agent_service.respond(agent_input)

        self._memory_service.append_message(
            session_id,
            MemoryEntry(role="user", content=payload.message),
        )
        self._memory_service.append_message(
            session_id,
            MemoryEntry(role="assistant", content=agent_output.message),
        )

        updated_state = self._memory_service.get_session_state(session_id)
        return ChatResponse(
            session_id=session_id,
            reply=agent_output.message,
            history=[
                ChatHistoryItem(
                    role=item.role,
                    content=item.content,
                    created_at=item.created_at,
                )
                for item in updated_state.messages
            ],
        )

    def reset_session(self, session_id: str) -> SessionResetResponse:
        cleared = self._memory_service.clear_session(session_id)
        return SessionResetResponse(session_id=session_id, cleared=cleared)

    def close(self) -> None:
        self._memory_service.close()
