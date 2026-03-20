from __future__ import annotations

import json
from typing import Literal

from openai import OpenAI
from pydantic import ValidationError

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput
from app.shared.exceptions import ConfigurationError, UpstreamServiceError
from app.shared.logging import get_logger
from app.shared.schemas import AIResponse, ResponseMetadata

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

    def generate(
        self, 
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat"
    ) -> AIResponse:
        """
        Generate response from OpenAI.
        
        Args:
            payload: Input including user message and history
            response_mode:
                - "chat": Returns plain conversational text wrapped in AIResponse
                - "tool_call": Returns structured JSON with tool actions
        """
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

        # In chat mode, we get plain text and wrap it
        # In tool_call mode, we enforce JSON structure
        if response_mode == "chat":
            return self._generate_chat_mode(messages)
        else:
            return self._generate_tool_mode(messages)
    
    def _generate_chat_mode(self, messages: list) -> AIResponse:
        """Generate normal conversational response without JSON enforcement."""
        try:
            logger.debug(
                "Sending chat mode request to OpenAI",
                extra={
                    "model": self._model,
                    "message_count": len(messages),
                    "response_mode": "chat",
                },
            )

            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                # No response_format constraint in chat mode
            )

            content = response.choices[0].message.content or ""
            
            if not content.strip():
                raise ValueError("AI returned empty response")
            
            logger.info(
                "Successfully generated chat response",
                extra={"content_length": len(content)}
            )
            
            # Wrap plain text in AIResponse structure
            return AIResponse(
                type="text",
                content=content,
                tool_action=None,
                metadata=ResponseMetadata()
            )
            
        except Exception as e:
            logger.error(
                "Error in chat mode generation",
                extra={"error": str(e)},
            )
            raise UpstreamServiceError(
                f"Failed to generate chat response from OpenAI: {e}"
            ) from e
    
    def _generate_tool_mode(self, messages: list) -> AIResponse:
        """Generate structured JSON response with tool actions."""
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                logger.debug(
                    "Sending tool mode request to OpenAI",
                    extra={
                        "model": self._model,
                        "message_count": len(messages),
                        "attempt": attempt + 1,
                        "response_mode": "tool_call",
                    },
                )

                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    response_format={"type": "json_object"}
                )

                ai_content = response.choices[0].message.content or ""
                
                logger.debug(
                    "Received response from OpenAI",
                    extra={
                        "content_length": len(ai_content),
                        "attempt": attempt + 1,
                    }
                )
                
                # Parse and validate
                ai_response_data = json.loads(ai_content)
                
                # Check for empty response
                if not ai_response_data or ai_response_data == {}:
                    raise ValueError("AI returned empty JSON object")
                
                ai_response = AIResponse(**ai_response_data)
                
                logger.info(
                    "Successfully generated valid AI response",
                    extra={"attempt": attempt + 1}
                )
                return ai_response
                
            except (ValidationError, ValueError, json.JSONDecodeError) as e:
                last_error = e
                logger.warning(
                    f"Invalid AI response on attempt {attempt + 1}/{max_retries}",
                    extra={
                        "error": str(e),
                        "attempt": attempt + 1,
                        "content": ai_content[:200] if 'ai_content' in locals() else None,
                    }
                )
                
                if attempt < max_retries - 1:
                    messages.append({
                        "role": "system",
                        "content": "CRITICAL: You must respond with valid JSON containing 'type', 'content', and 'metadata' fields. Never return an empty object."
                    })
                    continue
                else:
                    logger.error(
                        "All retry attempts failed for OpenAI",
                        extra={"validation_error": str(last_error)},
                    )
                    raise UpstreamServiceError(
                        f"OpenAI returned invalid response after {max_retries} attempts: {last_error}"
                    ) from last_error
                    
            except UpstreamServiceError:
                raise
            except Exception as e:
                logger.error(
                    "Error calling OpenAI",
                    extra={"error": str(e)},
                )
                raise UpstreamServiceError(
                    f"Failed to generate response from OpenAI: {e}"
                ) from e

