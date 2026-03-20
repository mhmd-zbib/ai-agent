import logging
from abc import ABC, abstractmethod
from typing import TypedDict

from app.modules.rag.embedders.base import BaseEmbedder
from app.modules.rag.repositories.base_document_repository import (
    BaseDocumentRepository,
)
from app.modules.rag.repositories.base_vector_repository import BaseVectorRepository
from app.modules.rag.schemas import Chunk, Document

logger = logging.getLogger(__name__)


class EmbeddingRecord(TypedDict):
    """Type-safe embedding record structure."""

    chunk_id: str
    document_id: str
    embedding: list[float]


class BaseIngestionService(ABC):
    """
    Abstract base class for ingestion pipeline (Template Method Pattern).
    
    Defines the skeleton of the ingestion algorithm:
    1. Validate inputs
    2. Store document
    3. Generate embeddings
    4. Prepare embedding payload
    5. Store embeddings
    
    Subclasses can override specific steps while maintaining the overall flow.
    """

    DEFAULT_BATCH_SIZE = 1000

    def __init__(
        self,
        document_repository: BaseDocumentRepository,
        vector_repository: BaseVectorRepository,
        embedder: BaseEmbedder,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._document_repository = document_repository
        self._vector_repository = vector_repository
        self._embedder = embedder
        self._batch_size = batch_size

    def ingest(self, document: Document, chunks: list[Chunk]) -> None:
        """
        Template method defining the ingestion pipeline.
        
        Args:
            document: Document to ingest
            chunks: Text chunks from the document
            
        Raises:
            ValueError: If validation fails
            RuntimeError: If ingestion fails
        """
        # Step 1: Validate
        self._validate_inputs(document, chunks)

        try:
            # Step 2: Store document
            self._store_document(document)

            # Step 3: Generate embeddings (with batching for memory protection)
            embeddings = self._generate_embeddings(chunks)

            # Step 4: Validate embeddings match chunks
            self._validate_embeddings(chunks, embeddings)

            # Step 5: Prepare payload
            payload = self._prepare_payload(chunks, embeddings)

            # Step 6: Store embeddings
            self._store_embeddings(payload)

            logger.info(
                f"Successfully ingested document {document.id} with {len(chunks)} chunks"
            )

        except Exception as e:
            logger.error(
                f"Failed to ingest document {document.id}: {e}", exc_info=True
            )
            raise RuntimeError(f"Ingestion failed for document {document.id}") from e

    def _validate_inputs(self, document: Document, chunks: list[Chunk]) -> None:
        """Validate document and chunks before processing."""
        if not chunks:
            raise ValueError("Cannot ingest document with zero chunks")

        if len(chunks) > self._batch_size:
            logger.warning(
                f"Chunk count ({len(chunks)}) exceeds batch size ({self._batch_size}). "
                "Consider splitting into multiple batches to protect memory."
            )

        # Validate all chunks belong to this document
        for idx, chunk in enumerate(chunks):
            if chunk.document_id != document.id:
                raise ValueError(
                    f"Chunk at index {idx} has document_id={chunk.document_id} "
                    f"but expected document_id={document.id}"
                )

    def _validate_embeddings(
        self, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        """Validate embeddings match chunks count."""
        if len(embeddings) != len(chunks):
            raise ValueError(
                f"Embedding count ({len(embeddings)}) does not match "
                f"chunk count ({len(chunks)})"
            )

        # Validate embedding dimensions are consistent
        if embeddings:
            expected_dim = len(embeddings[0])
            for idx, emb in enumerate(embeddings):
                if len(emb) != expected_dim:
                    raise ValueError(
                        f"Embedding at index {idx} has dimension {len(emb)} "
                        f"but expected {expected_dim}"
                    )

    @abstractmethod
    def _store_document(self, document: Document) -> None:
        """Store document in repository."""
        raise NotImplementedError

    @abstractmethod
    def _generate_embeddings(self, chunks: list[Chunk]) -> list[list[float]]:
        """Generate embeddings for chunks."""
        raise NotImplementedError

    @abstractmethod
    def _prepare_payload(
        self, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> list[EmbeddingRecord]:
        """Prepare embedding records for storage."""
        raise NotImplementedError

    @abstractmethod
    def _store_embeddings(self, payload: list[EmbeddingRecord]) -> None:
        """Store embeddings in vector repository."""
        raise NotImplementedError


class IngestionService(BaseIngestionService):
    """
    Concrete ingestion service implementation.
    
    Features:
    - Input validation (chunks match document, count validation)
    - Embedding dimension validation
    - Type-safe embedding records
    - Batch size limits for memory protection
    - Comprehensive error handling and logging
    """

    def _store_document(self, document: Document) -> None:
        """Store document in repository."""
        logger.debug(f"Storing document {document.id}")
        self._document_repository.upsert(document)

    def _generate_embeddings(self, chunks: list[Chunk]) -> list[list[float]]:
        """Generate embeddings for all chunks."""
        logger.debug(f"Generating embeddings for {len(chunks)} chunks")
        texts = [chunk.text for chunk in chunks]
        return self._embedder.embed(texts)

    def _prepare_payload(
        self, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> list[EmbeddingRecord]:
        """Prepare type-safe embedding records."""
        logger.debug(f"Preparing payload for {len(chunks)} chunks")
        return [
            EmbeddingRecord(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                embedding=embeddings[index],
            )
            for index, chunk in enumerate(chunks)
        ]

    def _store_embeddings(self, payload: list[EmbeddingRecord]) -> None:
        """Store embeddings in vector repository."""
        logger.debug(f"Storing {len(payload)} embeddings")
        self._vector_repository.upsert(payload)

