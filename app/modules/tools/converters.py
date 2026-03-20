from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.tools.base import BaseTool


def tools_to_openai_format(tools: list[BaseTool]) -> list[dict]:
    """
    Convert a list of BaseTool instances to OpenAI function calling format.
    
    Args:
        tools: List of tool instances to convert
        
    Returns:
        List of dictionaries in OpenAI tools format
        
    Example:
        >>> tools = [CalculatorTool(), WebSearchTool()]
        >>> openai_tools = tools_to_openai_format(tools)
        >>> # Pass to OpenAI API: client.chat.completions.create(..., tools=openai_tools)
    """
    return [tool.to_openai_tool() for tool in tools]
