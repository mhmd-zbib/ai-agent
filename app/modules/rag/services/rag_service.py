import logging

from app.modules.rag.repositories.base_vector_repository import BaseVectorRepository
from app.modules.rag.schemas import SearchQuery, SearchResult
from app.modules.rag.services.base_reranker import BaseReranker

logger = logging.getLogger(__name__)


class RAGService:
    """
    RAG (Retrieval-Augmented Generation) service.
    
    Orchestrates the retrieval pipeline:
    1. Vector similarity search
    2. Reranking for relevance
    
    Features:
    - Logging and observability
    - Graceful handling of stub implementations
    - Configurable search parameters
    """

    def __init__(
        self,
        vector_repository: BaseVectorRepository,
        reranker: BaseReranker,
        enable_reranking: bool = True,
    ) -> None:
        """
        Initialize RAG service.
        
        Args:
            vector_repository: Vector search implementation
            reranker: Reranking strategy
            enable_reranking: Whether to apply reranking (useful for testing/fallback)
        """
        self._vector_repository = vector_repository
        self._reranker = reranker
        self._enable_reranking = enable_reranking

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """
        Perform retrieval search with optional reranking.
        
        Args:
            query: Search query with text and parameters
            
        Returns:
            List of search results, reranked if enabled
            
        Raises:
            NotImplementedError: If vector repository is a stub
            RuntimeError: If search fails
        """
        logger.info(f"Searching for query: '{query.text}' (top_k={query.top_k})")

        try:
            # Step 1: Vector similarity search
            hits = self._vector_repository.search(query)
            logger.info(f"Vector search returned {len(hits)} results")

            if not hits:
                logger.warning("No results found for query")
                return []

            # Step 2: Optional reranking
            if self._enable_reranking:
                try:
                    reranked = self._reranker.rerank(hits)
                    logger.info(f"Reranked {len(hits)} results")
                    return reranked
                except NotImplementedError as e:
                    logger.warning(
                        f"Reranking not implemented, returning vector search results: {e}"
                    )
                    return hits
            else:
                logger.debug("Reranking disabled, returning vector search results")
                return hits

        except NotImplementedError:
            logger.error("Vector repository is a stub - cannot perform search")
            raise
        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            raise RuntimeError(f"Search failed for query: {query.text}") from e

