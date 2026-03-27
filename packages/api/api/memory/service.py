"""Memory service — dual-tier session storage (Redis hot + PostgreSQL cold)."""

# NOTE: This re-export is temporary during migration.
# The implementation still lives in api.modules.memory.services.memory_service
# but consumers should import from api.memory.service.
from api.modules.memory.services.memory_service import MemoryService

__all__ = ["MemoryService"]
