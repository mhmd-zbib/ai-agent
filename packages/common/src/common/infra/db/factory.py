"""
Vector client factory.

Selects the concrete IVectorClient implementation based on the VECTOR_BACKEND
setting (``qdrant`` or ``pinecone``) and returns a configured instance.
"""

from common.core.protocols import IVectorClient
from common.core.log_config import get_logger

logger = get_logger(__name__)


def create_vector_client(settings) -> IVectorClient:
    """
    Instantiate and return the configured vector backend.

    Args:
        settings: Application Settings instance.

    Returns:
        IVectorClient — either QdrantVectorClient or PineconeVectorClient.

    Raises:
        RuntimeError: If required credentials are missing for the selected backend.
    """
    if settings.vector_backend == "pinecone":
        if not settings.pinecone_api_key:
            raise RuntimeError(
                "PINECONE_API_KEY is required when VECTOR_BACKEND=pinecone"
            )
        from common.infra.db.pinecone import PineconeVectorClient

        logger.info(
            "Vector backend: Pinecone", extra={"index": settings.pinecone_index_name}
        )
        return PineconeVectorClient(
            api_key=settings.pinecone_api_key,
            index_name=settings.pinecone_index_name,
            dimension=settings.embedding_dimension,
            cloud=settings.pinecone_cloud,
            region=settings.pinecone_region,
        )

    # Default: Qdrant
    from common.infra.db.qdrant import QdrantVectorClient

    logger.info(
        "Vector backend: Qdrant",
        extra={
            "host": settings.qdrant_host,
            "port": settings.qdrant_port,
            "collection": settings.qdrant_collection,
        },
    )
    return QdrantVectorClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        collection_name=settings.qdrant_collection,
        dimension=settings.embedding_dimension,
    )


__all__ = ["create_vector_client"]
