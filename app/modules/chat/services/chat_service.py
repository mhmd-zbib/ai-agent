from uuid import uuid4
from typing import Literal

from app.modules.chat.schemas import ChatRequest, ChatResponse, SessionCreateResponse, SessionResetResponse
from app.shared.llm.base import BaseLLM
from app.shared.logging import get_logger
from app.shared.protocols import IMemoryService, IToolRegistry
from app.shared.schemas import AgentInput, AIResponse, MemoryEntry

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
        memory_service: IMemoryService,
        tool_registry: IToolRegistry,
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

        # Convert raw tool outage wording to conversational chat text.
        if tool_result.startswith("Weather service is currently unavailable"):
            return "I couldn't reach the weather service right now. Please try again in a moment."

        if ai_response.type == "tool":
            return tool_result

        if ai_response.type == "mixed":
            # Preserve model text and add tool output without implementation labels.
            base = ai_response.content.strip()
            return f"{base}\n\n{tool_result}" if base else tool_result

        return ai_response.content

    def _resolve_response_mode(self) -> Literal["chat", "tool_call"]:
        """Return response mode; kept isolated for future strategy injection."""
        return "chat"

    def _execute_tool_action(self, session_id: str, ai_response: AIResponse, user_id: str = "") -> AIResponse:
        """Execute tool action and update response content with user-safe output."""
        if ai_response.tool_action is None:
            return ai_response

        # Inject user_id so tools that need tenant-scoped data (e.g. document_lookup) can filter correctly.
        if user_id:
            ai_response.tool_action.params["user_id"] = user_id

        logger.info(
            "Tool action detected - executing",
            extra={
                "session_id": session_id,
                "tool_id": ai_response.tool_action.tool_id,
                "params": ai_response.tool_action.params,
            }
        )

        try:
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
            ai_response.content = self._format_user_content(ai_response, tool_result)
        except KeyError as exc:
            logger.error(
                "Tool not found",
                extra={
                    "session_id": session_id,
                    "tool_id": ai_response.tool_action.tool_id,
                    "error": str(exc),
                }
            )
            ai_response.content = "Sorry, I couldn't run that tool."
        except Exception as exc:
            logger.error(
                "Tool execution failed",
                extra={
                    "session_id": session_id,
                    "tool_id": ai_response.tool_action.tool_id,
                    "error": str(exc),
                }
            )
            ai_response.content = "Sorry, I hit an error while processing that request."

        return ai_response

    def _build_agent_input(self, payload: ChatRequest, state_messages: list[MemoryEntry]) -> AgentInput:
        return AgentInput(
            user_message=payload.message,
            session_id=payload.session_id,
            history=[{"role": item.role, "content": item.content} for item in state_messages],
        )

    def _build_followup_agent_input(
        self,
        payload: ChatRequest,
        state_messages: list[MemoryEntry],
        tool_observation: str,
    ) -> AgentInput:
        """Build a follow-up prompt so the model can finalize the full user answer."""
        followup_history = [
            {"role": item.role, "content": item.content}
            for item in state_messages
        ]
        followup_history.append({"role": "user", "content": payload.message})
        followup_history.append(
            {
                "role": "assistant",
                "content": (
                    "Tool observation:\n"
                    f"{tool_observation}\n\n"
                    "Now answer the user's full question in natural conversational text. "
                    "Do not output JSON."
                ),
            }
        )
        return AgentInput(
            user_message="Please provide the final user-facing answer.",
            session_id=payload.session_id,
            history=followup_history,
        )

    def _get_registered_tools(self) -> list[dict[str, object]]:
        return self._tool_registry.get_tools_for_openai()

    def _invoke_llm(
        self,
        agent_input: AgentInput,
        response_mode: Literal["chat", "tool_call"],
        tools: list[dict[str, object]] | None,
    ) -> AIResponse:
        return self._llm.generate(
            agent_input,
            response_mode=response_mode,
            tools=tools,
        )

    def _invoke_followup_answer(
        self,
        payload: ChatRequest,
        state_messages: list[MemoryEntry],
        tool_observation: str,
    ) -> str:
        """Ask the LLM to synthesize a final response using tool results."""
        followup_input = self._build_followup_agent_input(
            payload=payload,
            state_messages=state_messages,
            tool_observation=tool_observation,
        )
        followup_response = self._invoke_llm(
            agent_input=followup_input,
            response_mode="chat",
            tools=[],
        )
        return followup_response.content.strip() or tool_observation

    def _persist_turn(self, session_id: str, user_message: str, assistant_message: str) -> None:
        self._memory_service.append_message(
            session_id,
            MemoryEntry(role="user", content=user_message),
        )
        self._memory_service.append_message(
            session_id,
            MemoryEntry(role="assistant", content=assistant_message),
        )

    def _finalize_chat_response(self, ai_response: AIResponse) -> AIResponse:
        """Ensure chat mode returns conversational text instead of tool envelope."""
        ai_response.type = "text"
        ai_response.tool_action = None
        return ai_response

    def reply(self, payload: ChatRequest, user_id: str = "") -> ChatResponse:
        session_id = payload.session_id
        state = self._memory_service.get_session_state(session_id)

        agent_input = self._build_agent_input(payload=payload, state_messages=state.messages)

        # TODO: Determine response mode based on semantic tool search
        response_mode: Literal["chat", "tool_call"] = self._resolve_response_mode()

        tools = self._get_registered_tools()

        logger.debug(
            "Generating response",
            extra={
                "session_id": session_id,
                "response_mode": response_mode,
                "tool_count": len(tools),
            }
        )

        ai_response: AIResponse = self._invoke_llm(
            agent_input=agent_input,
            response_mode=response_mode,
            tools=tools,
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

        had_tool_action = ai_response.tool_action is not None
        ai_response = self._execute_tool_action(session_id=session_id, ai_response=ai_response, user_id=user_id)

        if had_tool_action:
            try:
                ai_response.content = self._invoke_followup_answer(
                    payload=payload,
                    state_messages=state.messages,
                    tool_observation=ai_response.content,
                )
            except Exception as exc:
                logger.warning(
                    "Follow-up synthesis failed; falling back to tool response",
                    extra={"session_id": session_id, "error": str(exc)},
                )

        ai_response = self._finalize_chat_response(ai_response)

        self._persist_turn(
            session_id=session_id,
            user_message=payload.message,
            assistant_message=ai_response.content,
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
