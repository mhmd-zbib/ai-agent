from app.modules.rag.repositories.vector_repository import VectorRepository
from app.modules.rag.schemas import SearchQuery, SearchResult
from app.modules.rag.services.reranker import Reranker


class RAGService:
    def __init__(self, vector_repository: VectorRepository, reranker: Reranker) -> None:
        self._vector_repository = vector_repository
        self._reranker = reranker

    def search(self, query: SearchQuery) -> list[SearchResult]:
        hits = self._vector_repository.search(query)
        return self._reranker.rerank(hits)

