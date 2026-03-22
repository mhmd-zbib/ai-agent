# Re-export the canonical protocol from shared.
# Import IFileStorage from here or from app.shared.protocols — they are the same.
from app.shared.protocols import IFileStorage

__all__ = ["IFileStorage"]
