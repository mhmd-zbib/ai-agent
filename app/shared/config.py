from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.shared.constants import DEFAULT_SYSTEM_PROMPT


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

    pinecone_api_key: str | None = Field(default=None, alias="PINECONE_API_KEY")
    pinecone_environment: str = Field(
        default="gcp-starter",
        alias="PINECONE_ENVIRONMENT",
    )
    pinecone_index_name: str = Field(
        default="agent-tools",
        alias="PINECONE_INDEX_NAME",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="EMBEDDING_MODEL",
    )
    embedding_dimension: int = Field(
        default=1536,
        alias="EMBEDDING_DIMENSION",
    )

    # Document pipeline infrastructure
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", alias="MINIO_SECRET_KEY")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")
    minio_bucket_name: str = Field(default="documents", alias="MINIO_BUCKET_NAME")

    rabbitmq_url: str = Field(
        default="amqp://guest:guest@localhost:5672/%2F",
        alias="RABBITMQ_URL",
    )
    rabbitmq_document_exchange: str = Field(
        default="documents.exchange",
        alias="RABBITMQ_DOCUMENT_EXCHANGE",
    )
    rabbitmq_document_routing_key: str = Field(
        default="documents.uploaded",
        alias="RABBITMQ_DOCUMENT_ROUTING_KEY",
    )
    rabbitmq_document_queue: str = Field(
        default="documents.uploaded.queue",
        alias="RABBITMQ_DOCUMENT_QUEUE",
    )
    document_chunk_size_bytes: int = Field(
        default=1024 * 1024,
        alias="DOCUMENT_CHUNK_SIZE_BYTES",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
