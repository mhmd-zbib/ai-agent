# Re-export canonical contracts from shared.
# Import IVectorClient and VectorRecord from here or from app.shared.protocols — they are the same.
from app.shared.protocols import IVectorClient, VectorRecord

__all__ = ["IVectorClient", "VectorRecord"]
