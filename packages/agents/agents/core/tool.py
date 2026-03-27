"""
agents.core.tool — BaseTool, ToolRegistry, and all tool exceptions.

Merges:
  packages/api/src/api/modules/tools/base.py
  packages/api/src/api/modules/tools/registry.py
  packages/api/src/api/modules/tools/exceptions.py

Import path for consumers:
  from agents.core.tool import BaseTool, ToolRegistry, ToolNotFoundError
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from shared.exceptions import AppError

__all__ = [
    "BaseTool",
    "ToolConfigurationError",
    "ToolException",
    "ToolExecutionError",
    "ToolInput",
    "ToolNotFoundError",
    "ToolOutput",
    "ToolRegistry",
    "ToolValidationError",
]

# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ToolInput:
    values: dict[str, Any]


@dataclass(slots=True)
class ToolOutput:
    value: str


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ToolException(AppError):
    """Base exception for all tool errors."""

    status_code = 500
    code = "tool_error"


class ToolNotFoundError(ToolException):
    """Tool with given ID not found in registry."""

    status_code = 404
    code = "tool_not_found"

    def __init__(self, tool_id: str) -> None:
        self.tool_id = tool_id
        super().__init__(f"Tool '{tool_id}' not found")


class ToolExecutionError(ToolException):
    """Tool execution failed."""

    status_code = 500
    code = "tool_execution_error"

    def __init__(self, tool_id: str, reason: str, user_message: str | None = None) -> None:
        self.tool_id = tool_id
        self.reason = reason
        self.user_message = user_message or f"Tool '{tool_id}' failed: {reason}"
        super().__init__(self.user_message)


class ToolConfigurationError(ToolException):
    """Tool is misconfigured."""

    status_code = 500
    code = "tool_configuration_error"

    def __init__(self, tool_id: str, issue: str) -> None:
        self.tool_id = tool_id
        self.issue = issue
        super().__init__(f"Tool '{tool_id}' configuration error: {issue}")


class ToolValidationError(ToolException):
    """Tool arguments failed validation."""

    status_code = 400
    code = "tool_validation_error"

    def __init__(self, tool_id: str, validation_errors: list[str]) -> None:
        self.tool_id = tool_id
        self.validation_errors = validation_errors
        super().__init__(
            f"Tool '{tool_id}' validation failed: {', '.join(validation_errors)}"
        )


# ---------------------------------------------------------------------------
# BaseTool
# ---------------------------------------------------------------------------


class BaseTool(ABC):
    """Abstract base class for all tool implementations."""

    name: str
    description: str
    parameters: dict[str, Any]

    @abstractmethod
    def run(self, arguments: dict[str, Any]) -> str:
        """
        Execute the tool with the provided arguments.

        This method must be implemented by all tool subclasses.
        It performs the tool's core functionality and returns the result.

        Args:
            arguments: Dictionary of arguments required by the tool,
                      matching the schema defined in self.parameters.

        Returns:
            String result of the tool execution. For structured results,
            return JSON-formatted strings.

        Raises:
            ToolExecutionError: If tool execution fails.
            ToolValidationError: If arguments are invalid.
        """
        ...

    def get_embedding_text(self) -> str:
        """
        Generate a combined text representation of the tool for semantic search.
        Combines name, description, and parameter information into a single string
        suitable for embedding generation.
        """
        parts = [
            f"Tool: {self.name}",
            f"Description: {self.description}",
        ]

        if self.parameters and "properties" in self.parameters:
            params_text = "Parameters: "
            param_details = []
            for param_name, param_info in self.parameters["properties"].items():
                param_type = param_info.get("type", "unknown")
                param_desc = param_info.get("description", "")
                required = param_name in self.parameters.get("required", [])
                req_marker = "(required)" if required else "(optional)"
                param_details.append(
                    f"{param_name} ({param_type}) {req_marker}: {param_desc}"
                )
            parts.append(params_text + "; ".join(param_details))

        return " | ".join(parts)

    def get_schema(self) -> dict[str, Any]:
        """
        Get the complete JSON schema representation of the tool.
        Useful for API integrations and documentation generation.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def to_openai_tool(self) -> dict[str, Any]:
        """
        Convert tool to OpenAI function calling format.

        Returns a dictionary compatible with OpenAI's tools parameter format.
        The parameters are already in JSON schema format, so no conversion needed.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Registry that holds and dispatches tool instances by name."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        name = tool.name.strip()
        if not name:
            raise ValueError("Tool name cannot be empty")
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = tool

    def resolve(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        return tool

    def list_tools(self) -> list[str]:
        """Return registered tool names in stable registration order."""
        return list(self._tools.keys())

    def get_tools_for_openai(self) -> list[dict[str, Any]]:
        """Get all registered tools in OpenAI function calling format.

        Returns list like:
        [
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Perform mathematical calculations",
                    "parameters": {...}
                }
            },
            ...
        ]
        """
        return [tool.to_openai_tool() for tool in self._tools.values()]
