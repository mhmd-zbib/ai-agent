"""Utility functions for working with LLM outputs.

This module provides safe JSON parsing utilities specifically designed for handling
LLM-generated content, which may include markdown code blocks or malformed JSON.
"""

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError
from structlog import get_logger

logger = get_logger(__name__)

__all__ = [
    "safe_json_parse",
    "safe_json_parse_with_schema",
]


def _strip_code_blocks(content: str) -> str:
    """Strip markdown code blocks from content.

    Removes ```json and ``` markers that LLMs often wrap JSON content with.

    Args:
        content: Raw string content potentially containing markdown code blocks

    Returns:
        Content with code blocks removed and whitespace stripped
    """
    # Remove opening code block marker (```json or ```)
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    # Remove closing code block marker
    content = re.sub(r"\s*```$", "", content.strip())
    return content.strip()


def safe_json_parse(content: str, strip_code_blocks: bool = True) -> tuple[dict[str, Any], bool]:
    """Safely parse JSON content, handling common LLM output formats.

    This function attempts to parse JSON content that may be wrapped in markdown
    code blocks or contain other formatting artifacts common in LLM outputs.

    Args:
        content: Raw string content to parse as JSON
        strip_code_blocks: If True, removes markdown code block markers before parsing

    Returns:
        A tuple of (parsed_dict, success):
        - parsed_dict: The parsed dictionary on success, empty dict on failure
        - success: True if parsing succeeded, False otherwise

    Examples:
        >>> safe_json_parse('{"key": "value"}')
        ({'key': 'value'}, True)

        >>> safe_json_parse('```json\\n{"key": "value"}\\n```')
        ({'key': 'value'}, True)

        >>> safe_json_parse('invalid json')
        ({}, False)
    """
    try:
        if strip_code_blocks:
            content = _strip_code_blocks(content)

        parsed = json.loads(content)

        if not isinstance(parsed, dict):
            logger.warning(
                "json_parse_not_dict",
                content_type=type(parsed).__name__,
            )
            return {}, False

        return parsed, True

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "json_parse_failed",
            error=str(e),
            content_preview=content[:100] if content else "",
        )
        return {}, False
    except Exception as e:
        logger.error(
            "json_parse_unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return {}, False


def safe_json_parse_with_schema(
    content: str,
    schema_cls: type[BaseModel],
) -> tuple[BaseModel | None, bool]:
    """Safely parse JSON content and validate against a Pydantic schema.

    This function combines JSON parsing with Pydantic validation, making it easy
    to parse and validate LLM outputs in a single call.

    Args:
        content: Raw string content to parse as JSON
        schema_cls: Pydantic model class to validate against

    Returns:
        A tuple of (schema_instance, success):
        - schema_instance: The validated Pydantic model instance on success, None on failure
        - success: True if parsing and validation succeeded, False otherwise

    Examples:
        >>> class UserSchema(BaseModel):
        ...     name: str
        ...     age: int

        >>> safe_json_parse_with_schema('{"name": "Alice", "age": 30}', UserSchema)
        (UserSchema(name='Alice', age=30), True)

        >>> safe_json_parse_with_schema('{"name": "Alice"}', UserSchema)
        (None, False)
    """
    try:
        # First parse the JSON
        parsed_dict, parse_success = safe_json_parse(content, strip_code_blocks=True)

        if not parse_success:
            return None, False

        # Then validate against schema
        validated = schema_cls.model_validate(parsed_dict)
        return validated, True

    except ValidationError as e:
        logger.warning(
            "schema_validation_failed",
            schema=schema_cls.__name__,
            errors=e.errors(),
        )
        return None, False
    except Exception as e:
        logger.error(
            "schema_validation_unexpected_error",
            schema=schema_cls.__name__,
            error=str(e),
            error_type=type(e).__name__,
        )
        return None, False
