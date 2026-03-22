# Re-export the canonical protocol from shared.
# Import IEmbeddingClient from here or from app.shared.protocols — they are the same.
from app.shared.protocols import IEmbeddingClient

__all__ = ["IEmbeddingClient"]
