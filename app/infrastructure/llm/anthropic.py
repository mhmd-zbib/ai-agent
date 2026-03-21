from typing import Any, Literal, Optional

from app.shared.exceptions import UpstreamServiceError
from app.shared.llm.base import BaseLLM
from app.shared.schemas import AgentInput, AIResponse


class AnthropicClient(BaseLLM):
    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AIResponse:  # noqa: ARG002
        raise UpstreamServiceError("Anthropic client is not configured yet.")
