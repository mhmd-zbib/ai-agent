from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolInput:
    values: dict[str, Any]


@dataclass(slots=True)
class ToolOutput:
    value: str


class BaseTool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]

    @abstractmethod
    def run(self, arguments: dict[str, Any]) -> str:
        raise NotImplementedError

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
