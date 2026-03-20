from abc import ABC, abstractmethod

from app.modules.rag.schemas import Document


class BaseDocumentRepository(ABC):
    """
    Abstract base class for document storage implementations (Repository Pattern).
    
    Document repositories are responsible for:
    - Storing raw documents and metadata
    - Retrieving documents by ID
    - Managing document lifecycle
    
    Implementations might include:
    - PostgreSQL
    - MongoDB
    - Elasticsearch
    - S3 + DynamoDB
    - In-memory (for testing)
    """

    @abstractmethod
    def upsert(self, document: Document) -> None:
        """
        Insert or update a document.

        Args:
            document: Document to store

        Raises:
            NotImplementedError: If implementation is not available
            ValueError: If document data is invalid
        """
        raise NotImplementedError

    @abstractmethod
    def get(self, document_id: str) -> Document | None:
        """
        Retrieve a document by ID.

        Args:
            document_id: Unique document identifier

        Returns:
            Document if found, None otherwise

        Raises:
            NotImplementedError: If implementation is not available
        """
        raise NotImplementedError
