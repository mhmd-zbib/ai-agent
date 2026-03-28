from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from .constants import DEFAULT_SYSTEM_PROMPT


class Settings(BaseSettings):
    app_name: str = "Agent Assistant API"
    app_version: str = "0.1.0"

    # OpenAI SDK settings (unified approach for all providers)
    openai_api_key: str = Field(
        default="not-needed",
        alias="OPENAI_API_KEY",
        description="API key for OpenAI. Use 'not-needed' for local providers like Ollama",
    )
    openai_model: str = Field(
        default="gpt-4-mini",
        alias="OPENAI_MODEL",
        description="Model name. Use OpenAI models (gpt-4-mini) or Ollama models (gemma3:270m)",
    )
    openai_base_url: str | None = Field(
        default=None,
        alias="OPENAI_BASE_URL",
        description=(
            "Optional base URL override for OpenAI SDK client. "
            "If None/empty: uses standard OpenAI endpoint (api.openai.com). "
            "If set: uses custom endpoint (e.g., http://localhost:11434/v1 for Ollama, "
            "Azure endpoints, or other OpenAI-compatible APIs)"
        ),
    )
    agent_system_prompt: str = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        alias="AGENT_SYSTEM_PROMPT",
    )

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    redis_chat_cache_ttl_seconds: int = Field(
        default=3600,
        alias="REDIS_CHAT_CACHE_TTL_SECONDS",
    )

    jwt_secret_key: str | None = Field(default=None, alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(
        default=60,
        alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Default admin account seeded on first startup (change via env vars)
    initial_admin_email: str = Field(
        default="admin@admin.com",
        alias="INITIAL_ADMIN_EMAIL",
    )
    initial_admin_password: str = Field(
        default="Admin123!",
        alias="INITIAL_ADMIN_PASSWORD",
    )

    enable_demo_tools: bool = Field(
        default=False,
        validation_alias="ENABLE_DEMO_TOOLS",
        description="Enable demo/showcase tools for development and testing",
    )

    postgres_pool_size: int = Field(default=5, alias="POSTGRES_POOL_SIZE")
    postgres_max_overflow: int = Field(default=10, alias="POSTGRES_MAX_OVERFLOW")
    postgres_pool_timeout_seconds: int = Field(
        default=30,
        alias="POSTGRES_POOL_TIMEOUT_SECONDS",
    )

    # Vector backend — "qdrant" (self-hosted) or "pinecone" (cloud SaaS)
    vector_backend: str = Field(default="qdrant", alias="VECTOR_BACKEND")

    # Qdrant (self-hosted, used when vector_backend=qdrant)
    qdrant_host: str = Field(default="localhost", alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, alias="QDRANT_PORT")
    qdrant_collection: str = Field(default="agent-documents", alias="QDRANT_COLLECTION")

    pinecone_api_key: str | None = Field(default=None, alias="PINECONE_API_KEY")
    pinecone_environment: str = Field(
        default="gcp-starter",
        alias="PINECONE_ENVIRONMENT",
    )
    pinecone_index_name: str = Field(
        default="agent-documents",
        alias="PINECONE_INDEX_NAME",
    )
    pinecone_cloud: str = Field(default="aws", alias="PINECONE_CLOUD")
    pinecone_region: str = Field(default="us-east-1", alias="PINECONE_REGION")
    embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="EMBEDDING_MODEL",
    )
    embedding_dimension: int = Field(
        default=1536,
        alias="EMBEDDING_DIMENSION",
    )
    # Embedding model credentials — independent of the chat LLM.
    # Falls back to OPENAI_API_KEY / OPENAI_BASE_URL when not explicitly set.
    embedding_api_key: str | None = Field(
        default=None,
        alias="EMBEDDING_API_KEY",
        description=(
            "API key for the embedding endpoint. "
            "Falls back to OPENAI_API_KEY when not set."
        ),
    )
    embedding_base_url: str | None = Field(
        default=None,
        alias="EMBEDDING_BASE_URL",
        description=(
            "Base URL for an OpenAI-compatible embedding endpoint. "
            "Leave empty to use the standard OpenAI API. "
            "Set to e.g. http://localhost:11434/v1 for Ollama embeddings."
        ),
    )
    embedding_max_retries: int = Field(
        default=3,
        alias="EMBEDDING_MAX_RETRIES",
        description="SDK-level retry attempts on 429 / 5xx before raising.",
    )

    model_config = SettingsConfigDict(
        populate_by_name=True,
        extra="ignore",
    )


class RagConfig(BaseSettings):
    """RAG service configuration."""

    fetch_multiplier: int = Field(
        default=4, description="Multiplier for initial fetch count"
    )
    min_relevance_score: float = Field(
        default=0.40, description="Minimum relevance score threshold"
    )

    model_config = SettingsConfigDict(env_prefix="RAG_")


class AgentConfig(BaseSettings):
    """Agent and orchestrator configuration."""

    default_temperature: float = Field(
        default=0.7, description="Default LLM temperature for general responses"
    )
    max_tokens: int = Field(default=2000, description="Max tokens per LLM response")
    planning_temperature: float = Field(
        default=0.5, description="Temperature for planning/orchestration LLM calls"
    )
    synthesis_temperature: float = Field(
        default=0.7, description="Temperature for synthesis LLM calls"
    )
    max_agent_iterations: int = Field(
        default=10, description="Max agent loop iterations before stopping"
    )
    max_llm_retries: int = Field(
        default=3, description="Max LLM retry attempts on parsing failures"
    )
    default_retrieval_top_k: int = Field(
        default=5, description="Default number of chunks to retrieve from vector DB"
    )
    orchestrator_history_window: int = Field(
        default=10,
        description="Number of recent turns to include in orchestrator planning",
    )
    reasoning_history_window: int = Field(
        default=6, description="Number of recent turns to include in reasoning agent"
    )
    default_confidence: float = Field(
        default=0.9, ge=0.0, le=1.0, description="Default confidence score"
    )
    fallback_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score for fallback responses",
    )
    critique_default_confidence: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Default confidence for critique fallback",
    )

    model_config = SettingsConfigDict(env_prefix="AGENT_")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
