"""core — shared contracts, schemas, and configuration."""

from .config import AgentConfig, RagConfig, Settings, get_settings
from .constants import DEFAULT_SYSTEM_PROMPT
from .enums import DegreeLevel, Role
from .exceptions import (
    AppError,
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    UpstreamServiceError,
    register_exception_handlers,
)
from .log_config import configure_logging, get_logger
from .llm_utils import safe_json_parse, safe_json_parse_with_schema
from .protocols import IEmbeddingClient, IMemoryService, IToolRegistry, IVectorClient
from .schemas import (
    AIResponse,
    AgentInput,
    MemoryEntry,
    ResponseMetadata,
    SessionState,
    ToolAction,
)
from .utils import strip_markdown_code_block

__all__ = [
    # Config
    "Settings",
    "get_settings",
    "RagConfig",
    "AgentConfig",
    # Enums
    "Role",
    "DegreeLevel",
    # Exceptions
    "AppError",
    "AuthenticationError",
    "ConfigurationError",
    "ConflictError",
    "UpstreamServiceError",
    "register_exception_handlers",
    # Logging
    "configure_logging",
    "get_logger",
    # Constants
    "DEFAULT_SYSTEM_PROMPT",
    # LLM Utils
    "safe_json_parse",
    "safe_json_parse_with_schema",
    # Protocols (contracts)
    "IMemoryService",
    "IToolRegistry",
    "IVectorClient",
    "IEmbeddingClient",
    # Schemas (data models)
    "AIResponse",
    "ToolAction",
    "ResponseMetadata",
    "AgentInput",
    "MemoryEntry",
    "SessionState",
    # Utils
    "strip_markdown_code_block",
]
