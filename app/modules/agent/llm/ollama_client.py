from __future__ import annotations

import json
from typing import Literal

from openai import OpenAI
from pydantic import ValidationError

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput
from app.shared.exceptions import UpstreamServiceError
from app.shared.logging import get_logger
from app.shared.schemas import AIResponse, ResponseMetadata

logger = get_logger(__name__)


class OllamaClient(BaseLLM):
    def __init__(self, host: str, model: str, system_prompt: str) -> None:
        # Ensure host ends with /v1 for OpenAI-compatible endpoint
        base_url = host.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        # Initialize OpenAI client with Ollama endpoint
        self._client = OpenAI(
            api_key="ollama",  # Ollama doesn't require real API key
            base_url=base_url
        )
        self._model = model
        self._system_prompt = system_prompt

        logger.info(
            "OllamaClient initialized with OpenAI SDK",
            extra={
                "base_url": base_url,
                "model": self._model,
            },
        )

    def generate(
        self, 
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat"
    ) -> AIResponse:
        """
        Generate response from Ollama.
        
        Args:
            payload: Input including user message and history
            response_mode:
                - "chat": Returns plain conversational text wrapped in AIResponse
                - "tool_call": Returns structured JSON with tool actions
        """
        # Build message array (same as OpenAI client)
        messages = [{"role": "system", "content": self._system_prompt}]
        messages.extend(
            {"role": item["role"], "content": item["content"]}
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
                "Sending chat mode request to Ollama",
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
                f"Failed to generate chat response from Ollama: {e}"
            ) from e
    
    def _generate_tool_mode(self, messages: list) -> AIResponse:
        """Generate structured JSON response with tool actions."""
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                logger.debug(
                    "Sending tool mode request to Ollama",
                    extra={
                        "model": self._model,
                        "message_count": len(messages),
                        "attempt": attempt + 1,
                        "response_mode": "tool_call",
                    },
                )

                # Use OpenAI SDK with JSON mode
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    response_format={"type": "json_object"}
                )
                
                # Extract content
                ai_content = response.choices[0].message.content or ""
                
                logger.debug(
                    "Received response from Ollama",
                    extra={
                        "content_length": len(ai_content),
                        "attempt": attempt + 1,
                    }
                )
                
                # Parse and validate AIResponse
                ai_response_data = json.loads(ai_content)
                
                # Check for empty response
                if not ai_response_data or ai_response_data == {}:
                    raise ValueError("AI returned empty JSON object")
                
                # Validate against schema
                ai_response = AIResponse(**ai_response_data)
                
                # Success! Return the response
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
                    # Add a message to the conversation encouraging proper format
                    messages.append({
                        "role": "system",
                        "content": "CRITICAL: You must respond with valid JSON containing 'type', 'content', and 'metadata' fields. Never return an empty object."
                    })
                    continue
                else:
                    # Final attempt failed
                    logger.error(
                        "All retry attempts failed for Ollama",
                        extra={"validation_error": str(last_error)},
                    )
                    raise UpstreamServiceError(
                        f"Ollama returned invalid response after {max_retries} attempts: {last_error}"
                    ) from last_error
                    
            except Exception as e:
                logger.error(
                    "Error calling Ollama via OpenAI SDK",
                    extra={"error": str(e)},
                )
                raise UpstreamServiceError(
                    f"Failed to generate response from Ollama: {e}"
                ) from e
