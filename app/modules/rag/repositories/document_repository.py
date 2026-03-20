import logging

from app.modules.rag.repositories.base_document_repository import (
    BaseDocumentRepository,
)
from app.modules.rag.schemas import Document

logger = logging.getLogger(__name__)


class DocumentRepository(BaseDocumentRepository):
    """
    Document repository stub implementation.
    
    This is a placeholder that should be replaced with a real database.
    
    Recommended implementations:
    - PostgreSQL: Relational DB with JSONB support
    - MongoDB: Document-oriented database
    - Elasticsearch: Full-text search capabilities
    
    Example real implementation with PostgreSQL:
        ```
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        class PostgresDocumentRepository(BaseDocumentRepository):
            def __init__(self, connection_string: str):
                self.conn = psycopg2.connect(connection_string)
            
            def upsert(self, document: Document) -> None:
                with self.conn.cursor() as cur:
                    cur.execute(
                        '''
                        INSERT INTO documents (id, title, content)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (id) DO UPDATE
                        SET title = EXCLUDED.title, content = EXCLUDED.content
                        ''',
                        (document.id, document.title, document.content)
                    )
                self.conn.commit()
            
            def get(self, document_id: str) -> Document | None:
                with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        'SELECT * FROM documents WHERE id = %s',
                        (document_id,)
                    )
                    row = cur.fetchone()
                    return Document(**row) if row else None
        ```
    
    Raises:
        NotImplementedError: This is a stub implementation
    """

    def upsert(self, document: Document) -> None:
        """
        Insert/update document (stub).
        
        Args:
            document: Document to store
            
        Raises:
            NotImplementedError: Document storage not yet implemented
        """
        logger.warning(
            f"DocumentRepository.upsert called for document {document.id} "
            "but not implemented"
        )
        raise NotImplementedError(
            "DocumentRepository is a stub. Implement with a database:\n"
            "- PostgreSQL: pip install psycopg2-binary\n"
            "- MongoDB: pip install pymongo\n"
            "- SQLAlchemy: pip install sqlalchemy\n"
            "Or use InMemoryDocumentRepository for testing"
        )

    def get(self, document_id: str) -> Document | None:
        """
        Retrieve document by ID (stub).
        
        Args:
            document_id: Document identifier
            
        Returns:
            Document if found, None otherwise
            
        Raises:
            NotImplementedError: Document retrieval not yet implemented
        """
        logger.warning(
            f"DocumentRepository.get called for document {document_id} "
            "but not implemented"
        )
        raise NotImplementedError(
            "DocumentRepository is a stub. Implement with a database. "
            "See class docstring for examples."
        )


class InMemoryDocumentRepository(BaseDocumentRepository):
    """Simple in-memory document repository for testing."""

    def __init__(self) -> None:
        self._documents: dict[str, Document] = {}

    def upsert(self, document: Document) -> None:
        """Store document in memory."""
        self._documents[document.id] = document
        logger.info(f"Stored document {document.id} in memory")

    def get(self, document_id: str) -> Document | None:
        """Retrieve document from memory."""
        return self._documents.get(document_id)

