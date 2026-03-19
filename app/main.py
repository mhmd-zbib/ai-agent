from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.modules.agent.llm.openai_client import OpenAIClient
from app.modules.agent.services.agent_service import AgentService
from app.modules.agent.services.tool_executor import ToolExecutor
from app.modules.chat.router import router as chat_router
from app.modules.chat.services.chat_service import ChatService
from app.modules.memory.repositories.long_term_repository import LongTermRepository
from app.modules.memory.repositories.short_term_repository import ShortTermRepository
from app.modules.memory.services.memory_service import MemoryService
from app.modules.tools import get_tool_registry
from app.modules.users.router import router as users_router
from app.shared.config import Settings, get_settings
from app.shared.db.postgres import create_postgres_engine
from app.shared.db.redis import create_redis_client
from app.shared.exceptions import ConfigurationError, register_exception_handlers


def create_chat_service(settings: Settings) -> ChatService:
    if not settings.database_url:
        raise ConfigurationError("DATABASE_URL is required.")
    if not settings.redis_url:
        raise ConfigurationError("REDIS_URL is required.")

    postgres_engine = create_postgres_engine(
        database_url=settings.database_url,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout_seconds=settings.postgres_pool_timeout_seconds,
    )
    redis_client = create_redis_client(settings.redis_url)

    long_term_repository = LongTermRepository(postgres_engine)
    long_term_repository.ensure_schema()
    short_term_repository = ShortTermRepository(
        redis_client=redis_client,
        ttl_seconds=settings.redis_chat_cache_ttl_seconds,
    )

    memory_service = MemoryService(
        short_term_repository=short_term_repository,
        long_term_repository=long_term_repository,
    )

    llm_client = OpenAIClient(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        system_prompt=settings.agent_system_prompt,
    )
    tool_executor = ToolExecutor(get_tool_registry())
    agent_service = AgentService(llm=llm_client, tool_executor=tool_executor)

    return ChatService(agent_service=agent_service, memory_service=memory_service)


def _startup_chat_service(app: FastAPI, settings: Settings) -> None:
    # Lifespan startup must be idempotent across test clients/reloads.
    if not hasattr(app.state, "chat_service"):
        app.state.chat_service = create_chat_service(settings)


def _shutdown_chat_service(app: FastAPI) -> None:
    chat_service = getattr(app.state, "chat_service", None)
    if chat_service is not None:
        chat_service.close()


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _startup_chat_service(app, settings)
        try:
            yield
        finally:
            _shutdown_chat_service(app)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.state.settings = settings

    app.include_router(chat_router)
    app.include_router(users_router)
    register_exception_handlers(app)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "message": "Agent Assistant API is running",
            "chat_endpoint": "/v1/agent/chat",
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

__all__ = ["app", "create_app", "create_chat_service"]
