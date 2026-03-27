"""Tool execution exceptions."""

from shared.exceptions import AppError

__all__ = [
    "ToolException",
    "ToolNotFoundError",
    "ToolExecutionError",
    "ToolConfigurationError",
    "ToolValidationError",
]


class ToolException(AppError):
    """Base exception for all tool errors."""

    status_code = 500
    code = "tool_error"


class ToolNotFoundError(ToolException):
    """Tool with given ID not found in registry."""

    status_code = 404
    code = "tool_not_found"

    def __init__(self, tool_id: str):
        self.tool_id = tool_id
        super().__init__(f"Tool '{tool_id}' not found")


class ToolExecutionError(ToolException):
    """Tool execution failed."""

    status_code = 500
    code = "tool_execution_error"

    def __init__(self, tool_id: str, reason: str, user_message: str | None = None):
        self.tool_id = tool_id
        self.reason = reason
        self.user_message = user_message or f"Tool '{tool_id}' failed: {reason}"
        super().__init__(self.user_message)


class ToolConfigurationError(ToolException):
    """Tool is misconfigured."""

    status_code = 500
    code = "tool_configuration_error"

    def __init__(self, tool_id: str, issue: str):
        self.tool_id = tool_id
        self.issue = issue
        super().__init__(f"Tool '{tool_id}' configuration error: {issue}")


class ToolValidationError(ToolException):
    """Tool arguments failed validation."""

    status_code = 400
    code = "tool_validation_error"

    def __init__(self, tool_id: str, validation_errors: list[str]):
        self.tool_id = tool_id
        self.validation_errors = validation_errors
        super().__init__(f"Tool '{tool_id}' validation failed: {', '.join(validation_errors)}")
