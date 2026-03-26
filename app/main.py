import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import Response
from redis import Redis
from sqlalchemy.engine import Engine

from app.infrastructure.database.postgres import create_postgres_engine
from app.infrastructure.database.redis import create_redis_client
from app.infrastructure.messaging.rabbitmq import (
    RabbitMQConsumer,
    RabbitMQPublisher,
    publish_to_queue,
    publish_batch_to_queue,
    setup_pipeline_topology,
)
from app.infrastructure.storage.minio import MinioStorageClient
from app.modules.agent.agents.action_agent import ActionAgent
from app.modules.agent.agents.critique_agent import CritiqueAgent
from app.modules.agent.agents.formula_verification_agent import FormulaVerificationAgent
from app.modules.agent.agents.memory_agent import MemoryAgent
from app.modules.agent.agents.reasoning_agent import ReasoningAgent
from app.modules.agent.agents.retrieval_agent import RetrievalAgent
from app.modules.agent.services.orchestrator_service import OrchestratorService
from app.modules.rag.services.rag_service import RAGService
from app.modules.rag.services.reranker import PassthroughReranker
from app.modules.chat.router import router as chat_router
from app.modules.chat.services.chat_service import ChatService
from app.modules.documents.repositories.document_event_repository import (
    RabbitMQDocumentEventRepository,
)
from app.modules.documents.repositories.document_storage_repository import (
    MinioDocumentStorageRepository,
)
from app.modules.documents.router import router as documents_router
from app.modules.documents.services import DocumentService
from app.modules.pipeline.repositories.document_status_repository import (
    DocumentStatusRepository,
)
from app.modules.memory.repositories.long_term_repository import LongTermRepository
from app.modules.memory.repositories.short_term_repository import ShortTermRepository
from app.modules.memory.services.memory_service import MemoryService
from app.modules.tools import get_tool_registry
from app.modules.users.config import AuthConfig
from app.modules.users.repositories.user_repository import UserRepository
from app.modules.users.router import router as users_router
from app.modules.users.services.auth_service import AuthService
from app.modules.users.services.user_service import UserService
from app.shared.config import AgentConfig, RagConfig, Settings, get_pipeline_config, get_settings
from app.shared.constants import (
    CRITIQUE_AGENT_SYSTEM_PROMPT,
    FORMULA_VERIFICATION_SYSTEM_PROMPT,
    MEMORY_AGENT_SYSTEM_PROMPT,
    ORCHESTRATOR_SYSTEM_PROMPT,
    REASONING_AGENT_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)
from app.shared.exceptions import ConfigurationError, register_exception_handlers
from app.infrastructure.llm.openai import OpenAIClient
from app.shared.llm.base import BaseLLM
from app.shared.logging import configure_logging, get_logger

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
) -> OrchestratorService:
    orchestrator_llm = _create_agent_llm(settings, ORCHESTRATOR_SYSTEM_PROMPT)
    synthesis_llm = _create_agent_llm(settings, SYNTHESIS_SYSTEM_PROMPT)
    reasoning_llm = _create_agent_llm(settings, REASONING_AGENT_SYSTEM_PROMPT)
    critique_llm = _create_agent_llm(settings, CRITIQUE_AGENT_SYSTEM_PROMPT)
    memory_llm = _create_agent_llm(settings, MEMORY_AGENT_SYSTEM_PROMPT)
    formula_verification_llm = _create_agent_llm(settings, FORMULA_VERIFICATION_SYSTEM_PROMPT)

    agent_config = AgentConfig()
    rag_config = RagConfig()
    rag_service = RAGService(
        vector_client=vector_client,
        embedding_client=embedding_client,
        reranker=PassthroughReranker(),
        rag_config=rag_config,
    )
    retrieval_agent = RetrievalAgent(rag_service=rag_service)

    return OrchestratorService(
        llm=orchestrator_llm,
        synthesis_llm=synthesis_llm,
        retrieval_agent=retrieval_agent,
        reasoning_agent=ReasoningAgent(llm=reasoning_llm, config=agent_config),
        critique_agent=CritiqueAgent(llm=critique_llm, config=agent_config),
        memory_agent=MemoryAgent(llm=memory_llm),
        action_agent=ActionAgent(tool_registry=tool_registry),
        formula_verification_agent=FormulaVerificationAgent(llm=formula_verification_llm),
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

    # Initialize RAG clients for document search tool and retrieval agent
    from app.infrastructure.embedding.openai import OpenAIEmbeddingClient
    from app.workers.store_consumer import _create_vector_client

    _embed_api_key = settings.embedding_api_key or settings.openai_api_key
    _embed_base_url = settings.embedding_base_url
    _rag_embedding_client = None
    _rag_vector_client = None

    if _embed_api_key and (_embed_api_key != "not-needed" or _embed_base_url):
        _rag_embedding_client = OpenAIEmbeddingClient(
            api_key=_embed_api_key,
            model=settings.embedding_model,
            base_url=_embed_base_url,
            dimensions=settings.embedding_dimension,
            max_retries=settings.embedding_max_retries,
        )
        try:
            _rag_vector_client = _create_vector_client(settings)
        except RuntimeError as exc:
            logger.warning("RAG vector client unavailable", extra={"reason": str(exc)})

    # Initialize tool system
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


def create_document_service(
    settings: Settings, postgres_engine: Engine
) -> DocumentService:
    storage_repo = MinioDocumentStorageRepository(
        MinioStorageClient(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket_name=settings.minio_bucket_name,
            secure=settings.minio_secure,
        )
    )
    # Fanout exchange so multiple consumers can bind (analytics, logging, etc.)
    event_repo = RabbitMQDocumentEventRepository(
        RabbitMQPublisher(
            amqp_url=settings.rabbitmq_url,
            exchange=settings.rabbitmq_document_fanout_exchange,
            routing_key="",  # Fanout ignores routing key
            exchange_type="fanout",
        )
    )
    status_repo = DocumentStatusRepository(postgres_engine)
    status_repo.ensure_schema()

    return DocumentService(
        bucket_name=settings.minio_bucket_name,
        default_chunk_size_bytes=settings.document_chunk_size_bytes,
        storage=storage_repo,
        event_publisher=event_repo,
        document_record_repository=status_repo,
    )


def _start_pipeline_workers(settings: Settings, postgres_engine: Engine) -> None:
    """
    Start the 4 RAG pipeline consumers as daemon threads.

    All workers share the same Postgres engine and MinIO client created at
    app startup. Each worker gets its own RabbitMQ channel (pika connections
    are not thread-safe, so each thread opens its own).

    Workers that require missing credentials (Pinecone, OpenAI) are skipped
    with a warning so the rest of the pipeline still starts.
    """
    from app.infrastructure.embedding.openai import OpenAIEmbeddingClient
    from app.modules.documents.schemas.events import DocumentUploadedEvent
    from app.modules.pipeline.repositories.document_status_repository import (
        DocumentStatusRepository,
    )
    from app.modules.pipeline.schemas.events import ChunkEvent, EmbedEvent, ParsedEvent
    from app.modules.pipeline.services.chunk_service import ChunkService
    from app.modules.pipeline.services.embed_service import EmbedService
    from app.modules.pipeline.services.parse_service import ParseService
    from app.modules.pipeline.services.store_service import StoreService

    # --- Shared services (created once, used across all worker threads) ---
    status_repo = DocumentStatusRepository(postgres_engine)
    status_repo.ensure_schema()

    storage = MinioStorageClient(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket_name=settings.minio_bucket_name,
        secure=settings.minio_secure,
    )

    parse_service = ParseService(storage=storage, status_repository=status_repo)
    chunk_service = ChunkService(
        storage=storage,
        status_repository=status_repo,
        window_tokens=settings.chunk_window_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
        encoding=settings.chunk_encoding,
    )

    # --- Handler functions (one per stage) ---
    def _parse_handler(payload: dict[str, Any]) -> None:
        event = DocumentUploadedEvent.model_validate(payload)
        parsed = parse_service.process(event)
        publish_to_queue(
            settings.rabbitmq_url,
            settings.rabbitmq_chunk_queue,
            parsed.model_dump(mode="json"),
        )

    def _chunk_handler(payload: dict[str, Any]) -> None:
        event = ParsedEvent.model_validate(payload)
        chunk_events = chunk_service.process(event)
        publish_batch_to_queue(
            settings.rabbitmq_url,
            settings.rabbitmq_embed_queue,
            [ce.model_dump(mode="json") for ce in chunk_events],
        )

    workers: list[tuple[str, str, str, Callable]] = [
        (
            "parse",
            settings.rabbitmq_parse_queue,
            settings.rabbitmq_parse_dlq,
            _parse_handler,
        ),
        (
            "chunk",
            settings.rabbitmq_chunk_queue,
            settings.rabbitmq_chunk_dlq,
            _chunk_handler,
        ),
    ]

    # Embed worker — needs a real API key OR a custom base_url (Ollama).
    # "not-needed" is valid when EMBEDDING_BASE_URL is set (e.g. Ollama).
    _embed_api_key = settings.embedding_api_key or settings.openai_api_key
    _embed_base_url = settings.embedding_base_url
    _embed_ready = bool(_embed_api_key) and (
        _embed_api_key != "not-needed" or bool(_embed_base_url)
    )
    if _embed_ready:
        _embedding_client = OpenAIEmbeddingClient(
            api_key=_embed_api_key,
            model=settings.embedding_model,
            base_url=settings.embedding_base_url,
            dimensions=settings.embedding_dimension,
            max_retries=settings.embedding_max_retries,
        )
        embed_service = EmbedService(
            embedding_client=_embedding_client,
            status_repository=status_repo,
        )

        def _embed_handler(payload: dict[str, Any]) -> None:
            event = ChunkEvent.model_validate(payload)
            embed_event = embed_service.process(event)
            publish_to_queue(
                settings.rabbitmq_url,
                settings.rabbitmq_store_queue,
                embed_event.model_dump(mode="json"),
            )

        workers.append(
            (
                "embed",
                settings.rabbitmq_embed_queue,
                settings.rabbitmq_embed_dlq,
                _embed_handler,
            )
        )
    else:
        logger.warning(
            "Embed worker not started: set EMBEDDING_API_KEY (or OPENAI_API_KEY) to enable embeddings"
        )

    # Store worker — backend selected by VECTOR_BACKEND env var
    from app.workers.store_consumer import _create_vector_client

    try:
        _vector_client = _create_vector_client(settings)
        pipeline_config = get_pipeline_config()
        store_service = StoreService(
            vector_client=_vector_client,
            status_repository=status_repo,
            pipeline_config=pipeline_config,
        )

        def _store_handler(payload: dict[str, Any]) -> None:
            event = EmbedEvent.model_validate(payload)
            store_service.process(event)

        workers.append(
            (
                "store",
                settings.rabbitmq_store_queue,
                settings.rabbitmq_store_dlq,
                _store_handler,
            )
        )
    except RuntimeError as exc:
        logger.warning("Store worker not started", extra={"reason": str(exc)})

    # --- Spawn a daemon thread per worker ---
    for name, queue, dlq, handler in workers:
        consumer = RabbitMQConsumer(
            amqp_url=settings.rabbitmq_url,
            queue_name=queue,
            dlq_name=dlq,
        )

        def _make_target(
            consumer: RabbitMQConsumer, handler: Callable, worker_name: str
        ) -> Callable:
            def _run() -> None:
                try:
                    consumer.consume_forever(handler)
                except Exception:
                    logger.exception(
                        "Pipeline worker crashed", extra={"worker": worker_name}
                    )

            return _run

        thread = threading.Thread(
            target=_make_target(consumer, handler, name),
            name=f"pipeline-{name}",
            daemon=True,
        )
        thread.start()
        logger.info("Pipeline worker started", extra={"worker": name, "queue": queue})


def _startup_services(app: FastAPI, settings: Settings) -> None:
    # Lifespan startup must be idempotent across test clients/reloads.
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

    if not hasattr(app.state, "document_service"):
        # Ensure the full pipeline topology exists in RabbitMQ before the first
        # document.uploaded event is published (idempotent, safe to call on every boot).
        try:
            setup_pipeline_topology(
                amqp_url=settings.rabbitmq_url,
                fanout_exchange=settings.rabbitmq_document_fanout_exchange,
                queues=[
                    (settings.rabbitmq_parse_queue, settings.rabbitmq_parse_dlq),
                    (settings.rabbitmq_chunk_queue, settings.rabbitmq_chunk_dlq),
                    (settings.rabbitmq_embed_queue, settings.rabbitmq_embed_dlq),
                    (settings.rabbitmq_store_queue, settings.rabbitmq_store_dlq),
                ],
            )
        except Exception:
            logger.warning(
                "Could not set up RabbitMQ pipeline topology — "
                "ensure RabbitMQ is running before uploading documents"
            )

        app.state.document_service = create_document_service(
            settings,
            app.state.postgres_engine,
        )

    if not hasattr(app.state, "pipeline_workers_started"):
        try:
            _start_pipeline_workers(settings, app.state.postgres_engine)
            app.state.pipeline_workers_started = True
        except Exception:
            logger.exception("Failed to start pipeline workers")


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
    "_create_agent_llm",
    "_create_llm_client",
    "app",
    "create_app",
    "create_chat_service",
    "create_document_service",
    "create_orchestrator_service",
    "create_user_service",
]
