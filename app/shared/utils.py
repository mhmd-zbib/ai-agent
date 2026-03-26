"""
Shared utility functions used across multiple modules.
"""

from __future__ import annotations


def strip_markdown_code_block(content: str) -> str:
    """
    Strip markdown code block markers from content.

    Removes the opening ```<lang> line and closing ``` line if present.
    Returns the content with leading/trailing whitespace stripped.

    Args:
        content: The content that may contain markdown code block markers

    Returns:
        The cleaned content without code block markers
    """
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)
    return content
