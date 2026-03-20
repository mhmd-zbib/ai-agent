from uuid import uuid4

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput
from app.modules.chat.schemas import ChatRequest, ChatResponse, SessionCreateResponse, SessionResetResponse
from app.modules.memory.schemas import MemoryEntry
from app.modules.memory.services.memory_service import MemoryService
from app.modules.tools.registry import ToolRegistry
from app.shared.logging import get_logger
from app.shared.schemas import AIResponse

logger = get_logger(__name__)


class ChatService:
    """
    Chat service that processes user messages and returns structured AI responses.
    
    This service determines the appropriate response mode:
    - "chat" mode: Normal conversational responses for general queries
    - "tool_call" mode: Structured JSON responses when tool execution is needed
    
    The response mode is currently defaulted to "chat" for all interactions.
    Future integration with semantic search will enable dynamic mode selection
    based on whether relevant tools are found for the user's query.
    """
    
    def __init__(
        self, 
        llm: BaseLLM, 
        memory_service: MemoryService,
        tool_registry: ToolRegistry
    ) -> None:
        self._llm = llm
        self._memory_service = memory_service
        self._tool_registry = tool_registry

    def create_session(self) -> SessionCreateResponse:
        session_id = str(uuid4())
        # Prime cache path so first chat turn uses Redis-first flow consistently.
        self._memory_service.get_session_state(session_id)
        return SessionCreateResponse(session_id=session_id)

    def _format_user_content(
        self,
        ai_response: AIResponse,
        tool_result: str | None = None,
    ) -> str:
        """Build clean user-facing content without transport/debug wrappers."""
        if tool_result is None:
            return ai_response.content

        if ai_response.type == "tool":
            return tool_result

        if ai_response.type == "mixed":
            # Preserve model text and add tool output without implementation labels.
            base = ai_response.content.strip()
            return f"{base}\n\n{tool_result}" if base else tool_result

        return ai_response.content

    def reply(self, payload: ChatRequest) -> ChatResponse:
        session_id = payload.session_id
        state = self._memory_service.get_session_state(session_id)

        agent_input = AgentInput(
            user_message=payload.message,
            session_id=session_id,
            history=[{"role": item.role, "content": item.content} for item in state.messages],
        )
        
        # TODO: Determine response mode based on semantic tool search
        # For now, default to "chat" mode for normal conversational responses
        # When tool integration is complete, this will check if relevant tools
        # were found via semantic search and switch to "tool_call" mode
        response_mode = "chat"  # Will be dynamic: "chat" | "tool_call"
        
        # Get tools from registry for OpenAI native function calling
        tools = self._tool_registry.get_tools_for_openai()
        
        logger.debug(
            "Generating response",
            extra={
                "session_id": session_id,
                "response_mode": response_mode,
                "tool_count": len(tools),
            }
        )
        
        # Get AIResponse from the LLM with appropriate mode and tools
        ai_response: AIResponse = self._llm.generate(
            agent_input, 
            response_mode=response_mode,
            tools=tools
        )
        
        logger.info(
            "Generated AI response",
            extra={
                "session_id": session_id,
                "response_type": ai_response.type,
                "response_mode": response_mode,
                "has_tool_action": ai_response.tool_action is not None,
                "confidence": ai_response.metadata.confidence if ai_response.metadata else None,
            }
        )
        
        # Process tool actions if present
        if ai_response.tool_action:
            logger.info(
                "Tool action detected - executing",
                extra={
                    "session_id": session_id,
                    "tool_id": ai_response.tool_action.tool_id,
                    "params": ai_response.tool_action.params,
                }
            )
            
            try:
                # Execute the tool
                tool = self._tool_registry.resolve(ai_response.tool_action.tool_id)
                tool_result = tool.run(ai_response.tool_action.params)

                logger.info(
                    "Tool execution completed",
                    extra={
                        "session_id": session_id,
                        "tool_id": ai_response.tool_action.tool_id,
                        "result_length": len(tool_result),
                    }
                )

                # Keep user output clean and free of internal wrapper labels.
                ai_response.content = self._format_user_content(ai_response, tool_result)

            except KeyError as e:
                logger.error(
                    "Tool not found",
                    extra={
                        "session_id": session_id,
                        "tool_id": ai_response.tool_action.tool_id,
                        "error": str(e),
                    }
                )
                ai_response.content = "Tool not found."

            except Exception as e:
                logger.error(
                    "Tool execution failed",
                    extra={
                        "session_id": session_id,
                        "tool_id": ai_response.tool_action.tool_id,
                        "error": str(e),
                    }
                )
                ai_response.content = f"Tool execution failed: {str(e)}"

        # Store user message in memory
        self._memory_service.append_message(
            session_id,
            MemoryEntry(role="user", content=payload.message),
        )
        
        # Store assistant response in memory
        # Only store the content field, not the full structured JSON
        self._memory_service.append_message(
            session_id,
            MemoryEntry(role="assistant", content=ai_response.content),
        )

        return ChatResponse(
            session_id=session_id,
            response_mode=response_mode,
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
