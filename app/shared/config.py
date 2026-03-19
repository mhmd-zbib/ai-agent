from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.shared.constants import DEFAULT_SYSTEM_PROMPT


class Settings(BaseSettings):
    app_name: str = "Agent Assistant API"
    app_version: str = "0.1.0"

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_base_url: str | None = Field(
        default=None,
        alias="OPENAI_BASE_URL",
        description="Custom base URL for OpenAI-compatible APIs (e.g., Ollama, Azure)",
    )
    agent_system_prompt: str = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        alias="AGENT_SYSTEM_PROMPT",
    )
    llm_provider: str = Field(default="ollama", alias="LLM_PROVIDER")
    ollama_host: str = Field(default="http://localhost:11434/v1", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="gemma3:270m", alias="OLLAMA_MODEL")

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

    postgres_pool_size: int = Field(default=5, alias="POSTGRES_POOL_SIZE")
    postgres_max_overflow: int = Field(default=10, alias="POSTGRES_MAX_OVERFLOW")
    postgres_pool_timeout_seconds: int = Field(
        default=30,
        alias="POSTGRES_POOL_TIMEOUT_SECONDS",
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
