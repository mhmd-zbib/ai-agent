"""Chat and AI pipeline service factories."""

from typing import Any

from redis import Redis
from sqlalchemy.engine import Engine

from api.chat.service import ChatService
from api.memory.repository import LongTermRepository, ShortTermRepository
from api.memory.service import MemoryService
from api.search.service import PassthroughReranker, RAGService
from common.agents.core.memory import MemoryAgent
from common.agents.document.agent import ActionAgent
from common.agents.extraction.agent import CritiqueAgent, FormulaVerificationAgent
from common.agents.orchestrator.agent import OrchestratorAgent
from common.agents.research.agent import ReasoningAgent, RetrievalAgent
from common.core.config import AgentConfig, RagConfig, Settings
from common.core.constants import (
    CRITIQUE_AGENT_SYSTEM_PROMPT,
    FORMULA_VERIFICATION_SYSTEM_PROMPT,
    MEMORY_AGENT_SYSTEM_PROMPT,
    ORCHESTRATOR_SYSTEM_PROMPT,
    REASONING_AGENT_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)
from common.core.log_config import get_logger
from common.infra.db.factory import create_vector_client
from common.infra.embedder import Embedder
from common.infra.llm.base import BaseLLM
from common.infra.llm.openai import OpenAIClient
from common.tools import get_tool_registry

logger = get_logger(__name__)


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
    agent_config = AgentConfig()
    rag_service = RAGService(
        vector_client=vector_client,
        embedding_client=embedding_client,
        reranker=PassthroughReranker(),
        rag_config=RagConfig(),
    )

    return OrchestratorAgent(
        llm=_create_agent_llm(settings, ORCHESTRATOR_SYSTEM_PROMPT),
        synthesis_llm=_create_agent_llm(settings, SYNTHESIS_SYSTEM_PROMPT),
        retrieval_agent=RetrievalAgent(rag_service=rag_service),
        reasoning_agent=ReasoningAgent(
            llm=_create_agent_llm(settings, REASONING_AGENT_SYSTEM_PROMPT),
            config=agent_config,
        ),
        critique_agent=CritiqueAgent(
            llm=_create_agent_llm(settings, CRITIQUE_AGENT_SYSTEM_PROMPT),
            config=agent_config,
        ),
        memory_agent=MemoryAgent(llm=_create_agent_llm(settings, MEMORY_AGENT_SYSTEM_PROMPT)),
        action_agent=ActionAgent(tool_registry=tool_registry),
        formula_verification_agent=FormulaVerificationAgent(
            llm=_create_agent_llm(settings, FORMULA_VERIFICATION_SYSTEM_PROMPT)
        ),
        config=agent_config,
    )


def create_chat_service(
    settings: Settings,
    postgres_engine: Engine,
    redis_client: Redis,
) -> ChatService:
    long_term_repo = LongTermRepository(postgres_engine)
    long_term_repo.ensure_schema()
    memory_service = MemoryService(
        short_term_repository=ShortTermRepository(
            redis_client=redis_client,
            ttl_seconds=settings.redis_chat_cache_ttl_seconds,
        ),
        long_term_repository=long_term_repo,
    )

    _embed_api_key = settings.embedding_api_key or settings.openai_api_key
    _embed_base_url = settings.embedding_base_url
    embedding_client = None
    vector_client = None

    if _embed_api_key and (_embed_api_key != "not-needed" or _embed_base_url):
        embedding_client = Embedder(
            api_key=_embed_api_key,
            model=settings.embedding_model,
            base_url=_embed_base_url,
            dimensions=settings.embedding_dimension,
            max_retries=settings.embedding_max_retries,
        )
        try:
            vector_client = create_vector_client(settings)
        except RuntimeError as exc:
            logger.warning("RAG vector client unavailable", extra={"reason": str(exc)})

    tool_registry = get_tool_registry(
        vector_client=vector_client,
        embedding_client=embedding_client,
    )
    logger.info(
        "Tool registry initialized",
        extra={"tool_count": len(tool_registry.list_tools()), "tools": tool_registry.list_tools()},
    )

    return ChatService(
        orchestrator_service=create_orchestrator_service(
            settings=settings,
            tool_registry=tool_registry,
            vector_client=vector_client,
            embedding_client=embedding_client,
        ),
        memory_service=memory_service,
    )
