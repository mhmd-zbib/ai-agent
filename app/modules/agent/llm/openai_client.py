from __future__ import annotations

import json
from typing import Any, Literal, Optional

from openai import OpenAI
from pydantic import ValidationError

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput
from app.shared.exceptions import ConfigurationError, UpstreamServiceError
from app.shared.logging import get_logger
from app.shared.schemas import AIResponse, ResponseMetadata, ToolAction

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
                # Ensure base_url ends with /v1 for OpenAI-compatible endpoints
                formatted_url = base_url.rstrip("/")
                if not formatted_url.endswith("/v1"):
                    formatted_url = f"{formatted_url}/v1"
                kwargs["base_url"] = formatted_url
                logger.info(
                    "OpenAIClient initialized with custom endpoint",
                    extra={
                        "base_url": formatted_url,
                        "model": model,
                    },
                )
            self._client = OpenAI(**kwargs)
        else:
            self._client = None
        self._model = model
        self._system_prompt = system_prompt

    def _chat_mode_instruction(self) -> str:
        """System-level instruction for conversational mode with tool calling."""
        return (
            "You are in chat mode. Respond in natural conversational text only. "
            "Do not return JSON objects or JSON code blocks. "
            "If a tool is needed, call the tool via tool_calls and keep content concise."
        )

    def _normalize_chat_content(self, content: str) -> str:
        """Convert accidental JSON string output into user-friendly plain text."""
        text = content.strip()
        if not text or not (text.startswith("{") and text.endswith("}")):
            return content

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return content

        if not isinstance(parsed, dict):
            return content

        # Structured schema output accidentally returned in chat mode.
        if isinstance(parsed.get("content"), str):
            return parsed["content"].strip()

        # Single-key payloads like {"weather": "..."} should be shown as plain text.
        if len(parsed) == 1:
            key, value = next(iter(parsed.items()))
            if isinstance(value, str) and value.strip():
                if key.lower() == "weather":
                    return f"The weather is {value.strip()}"
                return value.strip()

        # Last-resort flattening into readable text.
        parts: list[str] = []
        for key, value in parsed.items():
            if isinstance(value, str):
                parts.append(f"{key}: {value}")
        return "; ".join(parts) if parts else content

    def _build_messages(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"],
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt}]
        if response_mode == "chat":
            messages.append({"role": "system", "content": self._chat_mode_instruction()})
        messages.extend(
            {
                "role": item["role"],
                "content": item["content"],
            }
            for item in payload.history
        )
        messages.append({"role": "user", "content": payload.user_message})
        return messages

    def _build_chat_api_params(
        self,
        messages: list[dict[str, str]],
        tools: Optional[list[dict[str, Any]]],
    ) -> dict[str, Any]:
        api_params: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            api_params["tools"] = tools
            logger.debug(
                "Using OpenAI native function calling",
                extra={"tool_count": len(tools)},
            )
        return api_params

    def _classify_chat_response(
        self,
        content: str,
        parsed_tool_action: ToolAction | None,
    ) -> tuple[Literal["text", "tool", "mixed"], str]:
        if content and parsed_tool_action:
            logger.debug("Response contains both content and tool call")
            return "mixed", content

        if parsed_tool_action:
            logger.debug("Response contains only tool call")
            if not content:
                content = f"Calling tool: {parsed_tool_action.tool_id}"
            return "tool", content

        if not content.strip():
            raise ValueError("AI returned empty response")

        logger.debug("Response contains only text content")
        return "text", content

    def _parse_tool_mode_response(self, ai_content: str) -> AIResponse:
        ai_response_data = json.loads(ai_content)
        if not ai_response_data or ai_response_data == {}:
            raise ValueError("AI returned empty JSON object")
        return AIResponse(**ai_response_data)

    def _append_tool_mode_repair_instruction(self, messages: list[dict[str, str]]) -> None:
        messages.append(
            {
                "role": "system",
                "content": (
                    "CRITICAL: You must respond with valid JSON containing 'type', "
                    "'content', and 'metadata' fields. Never return an empty object."
                ),
            }
        )

    def _parse_tool_calls(self, tool_calls: list[Any]) -> ToolAction:
        valid_actions: list[ToolAction] = []
        invalid_calls = 0

        for idx, call in enumerate(tool_calls):
            tool_name = getattr(getattr(call, "function", None), "name", "")
            tool_args_str = getattr(getattr(call, "function", None), "arguments", "")

            logger.debug(
                "Parsing tool call",
                extra={
                    "tool_name": tool_name,
                    "args_length": len(tool_args_str),
                    "tool_call_index": idx,
                },
            )

            try:
                tool_args = json.loads(tool_args_str)
                valid_actions.append(ToolAction(tool_id=tool_name, params=tool_args))
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                invalid_calls += 1
                logger.warning(
                    "Skipping invalid tool call",
                    extra={
                        "tool_name": tool_name,
                        "tool_call_index": idx,
                        "error": str(exc),
                    },
                )

        if not valid_actions:
            raise ValueError("No valid tool calls could be parsed")

        selected_action = valid_actions[0]
        logger.info(
            "Successfully parsed tool calls",
            extra={
                "selected_tool_id": selected_action.tool_id,
                "valid_tool_calls": len(valid_actions),
                "invalid_tool_calls": invalid_calls,
                "total_tool_calls": len(tool_calls),
            },
        )
        return selected_action

    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None
    ) -> AIResponse:
        """
        Generate response from OpenAI.
        
        Args:
            payload: Input including user message and history
            response_mode:
                - "chat": Returns plain conversational text wrapped in AIResponse
                - "tool_call": Returns structured JSON with tool actions
            tools: Optional list of tools to provide to OpenAI for native function calling
        """
        if self._client is None:
            raise ConfigurationError("OPENAI_API_KEY is required to use the chat endpoint.")

        messages = self._build_messages(payload=payload, response_mode=response_mode)

        # In chat mode, we get plain text and wrap it
        # In tool_call mode, we enforce JSON structure
        if response_mode == "chat":
            return self._generate_chat_mode(messages, tools)
        return self._generate_tool_mode(messages)

    def _generate_chat_mode(
        self,
        messages: list,
        tools: Optional[list[dict[str, Any]]] = None
    ) -> AIResponse:
        """Generate normal conversational response with optional native function calling."""
        try:
            logger.debug(
                "Sending chat mode request to OpenAI",
                extra={
                    "model": self._model,
                    "message_count": len(messages),
                    "response_mode": "chat",
                    "tools_provided": tools is not None,
                },
            )

            api_params = self._build_chat_api_params(messages=messages, tools=tools)
            response = self._client.chat.completions.create(**api_params)

            msg = response.choices[0].message
            content = msg.content or ""
            tool_calls = msg.tool_calls
            if content and not tool_calls:
                content = self._normalize_chat_content(content)

            logger.debug(
                "Received response from OpenAI",
                extra={
                    "has_content": bool(content),
                    "has_tool_calls": bool(tool_calls),
                    "tool_call_count": len(tool_calls) if tool_calls else 0,
                }
            )
            
            # Parse tool_calls if present
            parsed_tool_action = None
            if tool_calls:
                parsed_tool_action = self._parse_tool_calls(tool_calls)

            response_type, content = self._classify_chat_response(
                content=content,
                parsed_tool_action=parsed_tool_action,
            )

            logger.info(
                "Successfully generated chat response",
                extra={
                    "response_type": response_type,
                    "content_length": len(content),
                    "has_tool_action": parsed_tool_action is not None,
                }
            )
            
            # Build AIResponse
            return AIResponse(
                type=response_type,
                content=content,
                tool_action=parsed_tool_action,
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
        last_error: Exception | None = None

        for attempt in range(max_retries):
            ai_content = ""
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
                    response_format={"type": "json_object"},
                )

                ai_content = response.choices[0].message.content or ""

                logger.debug(
                    "Received response from OpenAI",
                    extra={
                        "content_length": len(ai_content),
                        "attempt": attempt + 1,
                    }
                )

                ai_response = self._parse_tool_mode_response(ai_content)
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
                        "content": ai_content[:200] if ai_content else None,
                    }
                )

                if attempt < max_retries - 1:
                    self._append_tool_mode_repair_instruction(messages)
                    continue

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

