from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal, Optional

from app.modules.agent.schemas import AgentInput
from app.shared.schemas import AIResponse


class BaseLLM(ABC):
    @abstractmethod
    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AIResponse:
        """
        Generate a response from the LLM.

        Args:
            payload: Input data including user message and conversation history
            response_mode:
                - "chat": Normal conversational mode, returns plain text
                - "tool_call": Structured mode, enforces JSON with tool actions
            tools: Optional OpenAI-compatible function tool definitions

        Returns:
            AIResponse with content and optional tool actions
        """
        raise NotImplementedError
