from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal, Optional

from common.core.schemas import AgentInput, AIResponse


class BaseLLM(ABC):
    @abstractmethod
    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call", "json"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AIResponse:
        """
        Generate a response from the LLM.

        Args:
            payload: Input data including user message and conversation history
            response_mode:
                - "chat": Normal conversational mode, returns plain text
                - "tool_call": Structured mode, enforces JSON with tool actions
                - "json": Forces JSON output; raw JSON string returned in content
            tools: Optional OpenAI-compatible function tool definitions

        Returns:
            AIResponse with content and optional tool actions
        """
        raise NotImplementedError
