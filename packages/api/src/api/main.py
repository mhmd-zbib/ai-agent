from contextlib import asynccontextmanager
import os
from typing import Any, AsyncIterator

from common.agents.core.memory import MemoryAgent
from common.agents.document.agent import ActionAgent
from common.agents.extraction.agent import CritiqueAgent, FormulaVerificationAgent
from common.agents.orchestrator.agent import OrchestratorAgent
from common.agents.research.agent import ReasoningAgent, RetrievalAgent
from api.auth.config import AuthConfig
from api.auth.router import router as auth_router
from api.auth.service import AuthService, UserRepository, UserService
from api.chat.router import router as chat_router
from api.chat.service import ChatService
from api.documents.repository import MinIOBucketRepository, UploadSessionRepository
from api.documents.router import router as documents_router
from api.documents.service import DocumentUploadService
from api.health.router import router as health_router
from api.memory.repository import LongTermRepository, ShortTermRepository
from api.memory.service import MemoryService
from common.tools import get_tool_registry
from api.search.service import PassthroughReranker, RAGService
from fastapi import FastAPI, Request
from fastapi.responses import Response
from redis import Redis
from common.core.config import AgentConfig, RagConfig, Settings, get_settings
from common.core.constants import (
    CRITIQUE_AGENT_SYSTEM_PROMPT,
    FORMULA_VERIFICATION_SYSTEM_PROMPT,
    MEMORY_AGENT_SYSTEM_PROMPT,
    ORCHESTRATOR_SYSTEM_PROMPT,
    REASONING_AGENT_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)
from common.infra.db.factory import create_vector_client
from common.infra.db.postgres import create_postgres_engine
from common.infra.db.redis import create_redis_client
from common.infra.embedder import Embedder
from common.core.exceptions import ConfigurationError, register_exception_handlers
from common.infra.llm.base import BaseLLM
from common.infra.llm.openai import OpenAIClient
from common.core.log_config import configure_logging, get_logger
from common.infra.messaging.rabbitmq import RabbitMQPublisher
from common.infra.storage.minio import MinioStorageClient
from sqlalchemy.engine import Engine

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


def _create_agent_llm(settings: Settings, system_prompt: str) -> BaseLLM:
    return OpenAIClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        system_prompt=system_prompt,
    )


def create_orchestrator_service(
    settings: Settings,
    tool_registry: Any,
    vector_client: Any,
    embedding_client: Any,
) -> OrchestratorAgent:
    orchestrator_llm = _create_agent_llm(settings, ORCHESTRATOR_SYSTEM_PROMPT)
    synthesis_llm = _create_agent_llm(settings, SYNTHESIS_SYSTEM_PROMPT)
    reasoning_llm = _create_agent_llm(settings, REASONING_AGENT_SYSTEM_PROMPT)
    critique_llm = _create_agent_llm(settings, CRITIQUE_AGENT_SYSTEM_PROMPT)
    memory_llm = _create_agent_llm(settings, MEMORY_AGENT_SYSTEM_PROMPT)
    formula_verification_llm = _create_agent_llm(
        settings, FORMULA_VERIFICATION_SYSTEM_PROMPT
    )

    agent_config = AgentConfig()
    rag_config = RagConfig()
    rag_service = RAGService(
        vector_client=vector_client,
        embedding_client=embedding_client,
        reranker=PassthroughReranker(),
        rag_config=rag_config,
    )
    retrieval_agent = RetrievalAgent(rag_service=rag_service)

    return OrchestratorAgent(
        llm=orchestrator_llm,
        synthesis_llm=synthesis_llm,
        retrieval_agent=retrieval_agent,
        reasoning_agent=ReasoningAgent(llm=reasoning_llm, config=agent_config),
        critique_agent=CritiqueAgent(llm=critique_llm, config=agent_config),
        memory_agent=MemoryAgent(llm=memory_llm),
        action_agent=ActionAgent(tool_registry=tool_registry),
        formula_verification_agent=FormulaVerificationAgent(
            llm=formula_verification_llm
        ),
        config=agent_config,
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

    _embed_api_key = settings.embedding_api_key or settings.openai_api_key
    _embed_base_url = settings.embedding_base_url
    _rag_embedding_client = None
    _rag_vector_client = None

    if _embed_api_key and (_embed_api_key != "not-needed" or _embed_base_url):
        _rag_embedding_client = Embedder(
            api_key=_embed_api_key,
            model=settings.embedding_model,
            base_url=_embed_base_url,
            dimensions=settings.embedding_dimension,
            max_retries=settings.embedding_max_retries,
        )
        try:
            _rag_vector_client = create_vector_client(settings)
        except RuntimeError as exc:
            logger.warning("RAG vector client unavailable", extra={"reason": str(exc)})

    tool_registry = get_tool_registry(
        vector_client=_rag_vector_client,
        embedding_client=_rag_embedding_client,
    )
    logger.info(
        "Tool registry initialized",
        extra={
            "tool_count": len(tool_registry.list_tools()),
            "tools": tool_registry.list_tools(),
        },
    )

    orchestrator_service = create_orchestrator_service(
        settings=settings,
        tool_registry=tool_registry,
        vector_client=_rag_vector_client,
        embedding_client=_rag_embedding_client,
    )

    return ChatService(
        orchestrator_service=orchestrator_service,
        memory_service=memory_service,
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


def create_document_upload_service(
    settings: Settings, redis_client: Redis
) -> DocumentUploadService:
    """Create document upload service with MinIO bucket and RabbitMQ."""
    session_repo = UploadSessionRepository(redis_client)

    minio_client = MinioStorageClient(
        endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        bucket_name=os.getenv("MINIO_BUCKET_NAME", "documents"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )
    bucket_repo = MinIOBucketRepository(minio_client)

    rabbitmq_publisher = RabbitMQPublisher(
        amqp_url=os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F"),
        exchange=os.getenv("RABBITMQ_DOCUMENT_EXCHANGE", "documents.exchange"),
        routing_key=os.getenv("RABBITMQ_DOCUMENT_ROUTING_KEY", "documents.uploaded"),
        exchange_type="topic",
    )

    return DocumentUploadService(
        session_repo=session_repo,
        bucket_repo=bucket_repo,
        rabbitmq_publisher=rabbitmq_publisher,
    )


def _startup_services(app: FastAPI, settings: Settings) -> None:
    if not hasattr(app.state, "postgres_engine") or not hasattr(
        app.state, "redis_client"
    ):
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

    if not hasattr(app.state, "document_upload_service"):
        app.state.document_upload_service = create_document_upload_service(
            settings=settings,
            redis_client=app.state.redis_client,
        )


def _shutdown_services(app: FastAPI) -> None:
    chat_service = getattr(app.state, "chat_service", None)
    if chat_service is not None:
        chat_service.close()

    user_service = getattr(app.state, "user_service", None)
    if user_service is not None:
        user_service.close()


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

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id")
        if request_id:
            request.state.request_id = request_id
        response = await call_next(request)
        if request_id:
            response.headers["x-request-id"] = request_id
        return response

    app.include_router(chat_router)
    app.include_router(auth_router)
    app.include_router(documents_router)
    app.include_router(health_router)
    register_exception_handlers(app)

    return app


app = create_app()

__all__ = [
    "_create_agent_llm",
    "app",
    "create_app",
    "create_chat_service",
    "create_orchestrator_service",
    "create_user_service",
]