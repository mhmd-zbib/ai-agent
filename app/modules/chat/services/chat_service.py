import json
from uuid import uuid4

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput
from app.modules.chat.schemas import ChatRequest, ChatResponse, SessionCreateResponse, SessionResetResponse
from app.modules.memory.schemas import MemoryEntry
from app.modules.memory.services.memory_service import MemoryService
from app.shared.logging import get_logger
from app.shared.schemas import AIResponse

logger = get_logger(__name__)


class ChatService:
    """
    Chat service that processes user messages and returns structured AI responses.
    
    This service now works directly with AIResponse objects from the LLM,
    processing structured JSON responses including type, content, tool actions,
    and metadata.
    """
    
    def __init__(self, llm: BaseLLM, memory_service: MemoryService) -> None:
        self._llm = llm
        self._memory_service = memory_service

    def create_session(self) -> SessionCreateResponse:
        session_id = str(uuid4())
        # Prime cache path so first chat turn uses Redis-first flow consistently.
        self._memory_service.get_session_state(session_id)
        return SessionCreateResponse(session_id=session_id)

    def reply(self, payload: ChatRequest) -> ChatResponse:
        session_id = payload.session_id
        state = self._memory_service.get_session_state(session_id)

        agent_input = AgentInput(
            user_message=payload.message,
            session_id=session_id,
            history=[{"role": item.role, "content": item.content} for item in state.messages],
        )
        
        # Get structured AIResponse from the LLM
        ai_response: AIResponse = self._llm.generate(agent_input)
        
        logger.info(
            "Generated AI response",
            extra={
                "session_id": session_id,
                "response_type": ai_response.type,
                "has_tool_action": ai_response.tool_action is not None,
                "confidence": ai_response.metadata.confidence,
            }
        )
        
        # Process tool actions if present
        if ai_response.tool_action:
            logger.info(
                "Tool action detected",
                extra={
                    "session_id": session_id,
                    "tool_id": ai_response.tool_action.tool_id,
                    "params": ai_response.tool_action.params,
                }
            )
            # TODO: Execute tool action and update response with results
            # This will be implemented when tool executor is integrated
        
        # Store user message in memory
        self._memory_service.append_message(
            session_id,
            MemoryEntry(role="user", content=payload.message),
        )
        
        # Store assistant response in memory as JSON for structured storage
        assistant_content = json.dumps({
            "type": ai_response.type,
            "content": ai_response.content,
            "tool_action": ai_response.tool_action.model_dump() if ai_response.tool_action else None,
            "metadata": ai_response.metadata.model_dump(),
        })
        
        self._memory_service.append_message(
            session_id,
            MemoryEntry(role="assistant", content=assistant_content),
        )

        return ChatResponse(
            session_id=session_id,
            type=ai_response.type,
            content=ai_response.content,
            tool_action=ai_response.tool_action,
            metadata=ai_response.metadata,
        )

    def reset_session(self, session_id: str) -> SessionResetResponse:
        cleared = self._memory_service.clear_session(session_id)
        return SessionResetResponse(session_id=session_id, cleared=cleared)

    def close(self) -> None:
        self._memory_service.close()
