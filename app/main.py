from contextlib import asynccontextmanager
from typing import AsyncIterator, cast

from fastapi import FastAPI
from redis import Redis
from sqlalchemy.engine import Engine

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.llm.openai_client import OpenAIClient
from app.modules.chat.router import router as chat_router
from app.modules.chat.services.chat_service import ChatService
from app.modules.documents.router import router as documents_router
from app.modules.documents.services import DocumentService
from app.modules.documents.services.document_service import EventPublisherPort
from app.modules.documents.services.document_service import DocumentStoragePort
from app.modules.memory.repositories.long_term_repository import LongTermRepository
from app.modules.memory.repositories.short_term_repository import ShortTermRepository
from app.modules.memory.services.memory_service import MemoryService
from app.modules.tools import get_tool_registry
from app.modules.users.config import AuthConfig
from app.modules.users.repositories.user_repository import UserRepository
from app.modules.users.router import router as users_router
from app.modules.users.services.auth_service import AuthService
from app.modules.users.services.user_service import UserService
from app.shared.config import Settings, get_settings
from app.shared.db.postgres import create_postgres_engine
from app.shared.db.redis import create_redis_client
from app.shared.exceptions import ConfigurationError, register_exception_handlers
from app.shared.logging import configure_logging, get_logger
from app.shared.messaging import RabbitMQPublisher
from app.shared.storage import MinioStorageClient

logger = get_logger(__name__)


def _create_infrastructure(settings: Settings) -> tuple[Engine, Redis]:
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
    return postgres_engine, redis_client


def _create_llm_client(settings: Settings) -> BaseLLM:
    return OpenAIClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        system_prompt=settings.agent_system_prompt,
    )


def create_chat_service(
    settings: Settings,
    postgres_engine: Engine,
    redis_client: Redis,
) -> ChatService:
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

    llm_client = _create_llm_client(settings)
    
    # Initialize tool system
    tool_registry = get_tool_registry()
    logger.info(
        "Tool registry initialized",
        extra={
            "tool_count": len(tool_registry.list_tools()),
            "tools": tool_registry.list_tools(),
        }
    )

    return ChatService(
        llm=llm_client, 
        memory_service=memory_service,
        tool_registry=tool_registry
    )


def create_user_service(settings: Settings, postgres_engine: Engine) -> UserService:
    auth_config = AuthConfig(
        settings.jwt_secret_key or "",
        settings.jwt_algorithm,
        settings.jwt_access_token_expire_minutes,
    )
    auth_service = AuthService(auth_config)
    user_repository = UserRepository(postgres_engine)
    user_repository.ensure_schema()
    return UserService(repository=user_repository, auth_service=auth_service)


def create_document_service(settings: Settings) -> DocumentService:
    storage = MinioStorageClient(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket_name=settings.minio_bucket_name,
        secure=settings.minio_secure,
    )
    publisher = RabbitMQPublisher(
        amqp_url=settings.rabbitmq_url,
        exchange=settings.rabbitmq_document_exchange,
        routing_key=settings.rabbitmq_document_routing_key,
    )
    return DocumentService(
        bucket_name=settings.minio_bucket_name,
        default_chunk_size_bytes=settings.document_chunk_size_bytes,
        storage=cast(DocumentStoragePort, cast(object, storage)),
        event_publisher=cast(EventPublisherPort, cast(object, publisher)),
    )


def _startup_services(app: FastAPI, settings: Settings) -> None:
    # Lifespan startup must be idempotent across test clients/reloads.
    if not hasattr(app.state, "postgres_engine") or not hasattr(app.state, "redis_client"):
        postgres_engine, redis_client = _create_infrastructure(settings)
        app.state.postgres_engine = postgres_engine
        app.state.redis_client = redis_client

    if not hasattr(app.state, "chat_service"):
        app.state.chat_service = create_chat_service(
            settings=settings,
            postgres_engine=app.state.postgres_engine,
            redis_client=app.state.redis_client,
        )

    if not hasattr(app.state, "user_service"):
        app.state.user_service = create_user_service(
            settings=settings,
            postgres_engine=app.state.postgres_engine,
        )

    if not hasattr(app.state, "document_service"):
        app.state.document_service = create_document_service(settings)


def _shutdown_services(app: FastAPI) -> None:
    chat_service = getattr(app.state, "chat_service", None)
    if chat_service is not None:
        chat_service.close()

    user_service = getattr(app.state, "user_service", None)
    if user_service is not None:
        user_service.close()

    document_service = getattr(app.state, "document_service", None)
    if document_service is not None:
        document_service.close()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _startup_services(app, settings)
        try:
            yield
        finally:
            _shutdown_services(app)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.state.settings = settings

    app.include_router(chat_router)
    app.include_router(users_router)
    app.include_router(documents_router)
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

__all__ = [
    "app",
    "create_app",
    "create_chat_service",
    "create_user_service",
    "create_document_service",
    "_create_llm_client",
]
