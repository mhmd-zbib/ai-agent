from __future__ import annotations

import json

from openai import OpenAI
from pydantic import ValidationError

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput
from app.shared.exceptions import ConfigurationError, UpstreamServiceError
from app.shared.logging import get_logger
from app.shared.schemas import AIResponse

logger = get_logger(__name__)


class OpenAIClient(BaseLLM):
    def __init__(
        self,
        api_key: str | None,
        base_url: str | None,
        model: str,
        system_prompt: str
    ) -> None:
        if api_key:
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = OpenAI(**kwargs)
        else:
            self._client = None
        self._model = model
        self._system_prompt = system_prompt

    def generate(self, payload: AgentInput) -> AIResponse:
        if self._client is None:
            raise ConfigurationError("OPENAI_API_KEY is required to use the chat endpoint.")

        # Build simple message array for Chat Completions API
        messages = [{"role": "system", "content": self._system_prompt}]
        messages.extend(
            {
                "role": item["role"],
                "content": item["content"]
            }
            for item in payload.history
        )
        messages.append({"role": "user", "content": payload.user_message})

        try:
            # Use correct Chat Completions API
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"}
            )
            # Extract content from correct location
            ai_content = response.choices[0].message.content or ""
            if not ai_content.strip():
                raise UpstreamServiceError("OpenAI returned an empty response.")

            # Parse the AI's JSON response
            try:
                ai_response_data = json.loads(ai_content)
            except json.JSONDecodeError as exc:
                logger.error(
                    "OpenAI returned invalid JSON content",
                    extra={
                        "ai_content": ai_content[:500],
                    },
                    exc_info=True,
                )
                raise UpstreamServiceError(
                    "OpenAI returned malformed JSON. Expected AIResponse schema."
                ) from exc

            # Validate and construct AIResponse object
            try:
                ai_response = AIResponse(**ai_response_data)
            except ValidationError as exc:
                logger.error(
                    "OpenAI response failed schema validation",
                    extra={
                        "validation_errors": exc.errors(),
                        "ai_response_data": ai_response_data,
                    },
                    exc_info=True,
                )
                raise UpstreamServiceError(
                    f"OpenAI response does not match expected schema: {exc}"
                ) from exc

            logger.info(
                "Successfully parsed AI response from OpenAI",
                extra={
                    "response_type": ai_response.type,
                    "has_tool_action": ai_response.tool_action is not None,
                    "confidence": ai_response.metadata.confidence,
                },
            )

            return ai_response

        except UpstreamServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to generate response from OpenAI",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
            raise UpstreamServiceError("Failed to generate a response from OpenAI.") from exc

