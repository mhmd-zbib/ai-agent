from abc import ABC, abstractmethod

from app.modules.rag.schemas import SearchResult


class BaseReranker(ABC):
    """Abstract base class for reranking strategies (Strategy Pattern)."""

    @abstractmethod
    def rerank(self, items: list[SearchResult]) -> list[SearchResult]:
        """
        Rerank search results based on implementation-specific logic.

        Args:
            items: List of search results to rerank

        Returns:
            Reranked list of search results

        Raises:
            NotImplementedError: If the implementation is not available
        """
        raise NotImplementedError
