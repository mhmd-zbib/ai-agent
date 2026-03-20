from abc import ABC, abstractmethod

from app.modules.rag.schemas import SearchQuery, SearchResult


class BaseVectorRepository(ABC):
    """
    Abstract base class for vector storage implementations (Repository Pattern).
    
    Vector repositories are responsible for:
    - Storing vector embeddings with metadata
    - Performing similarity search (e.g., cosine, euclidean)
    - Managing vector indices
    
    Implementations might include:
    - Pinecone
    - Qdrant
    - Weaviate
    - Milvus
    - PostgreSQL with pgvector
    - In-memory (for testing)
    """

    @abstractmethod
    def search(self, query: SearchQuery) -> list[SearchResult]:
        """
        Perform similarity search for query.

        Args:
            query: Search query with text and parameters

        Returns:
            List of search results with scores

        Raises:
            NotImplementedError: If implementation is not available
        """
        raise NotImplementedError

    @abstractmethod
    def upsert(self, embeddings: list[dict[str, object]]) -> None:
        """
        Insert or update vector embeddings.

        Args:
            embeddings: List of embedding records containing:
                - chunk_id: Unique chunk identifier
                - document_id: Parent document identifier
                - embedding: Vector embedding (list of floats)

        Raises:
            NotImplementedError: If implementation is not available
            ValueError: If embedding data is malformed
        """
        raise NotImplementedError
