from app.modules.rag.embedders.base import BaseEmbedder
from app.modules.rag.repositories import DocumentRepository, VectorRepository
from app.modules.rag.schemas import Chunk, Document


class IngestionService:
    def __init__(
        self,
        document_repository: DocumentRepository,
        vector_repository: VectorRepository,
        embedder: BaseEmbedder,
    ) -> None:
        self._document_repository = document_repository
        self._vector_repository = vector_repository
        self._embedder = embedder

    def ingest(self, document: Document, chunks: list[Chunk]) -> None:
        self._document_repository.upsert(document)
        embeddings = self._embedder.embed([chunk.text for chunk in chunks])
        payload = [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "embedding": embeddings[index],
            }
            for index, chunk in enumerate(chunks)
        ]
        self._vector_repository.upsert(payload)

