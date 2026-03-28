from collections import OrderedDict
from typing import Protocol

from common.core.log_config import get_logger
from common.core.schemas import MemoryEntry, SessionState

logger = get_logger(__name__)


class ShortTermRepositoryProtocol(Protocol):
    """Protocol for short-term repository (enables testing without concrete type)."""

    def get_messages(self, session_id: str) -> list[MemoryEntry] | None: ...
    def set_messages(self, session_id: str, messages: list[MemoryEntry]) -> bool: ...
    def delete_messages(self, session_id: str) -> bool: ...
    def get_metadata(self, session_id: str, key: str) -> str | None: ...
    def set_metadata(self, session_id: str, key: str, value: str) -> bool: ...
    def delete_metadata(self, session_id: str, key: str) -> bool: ...


class LongTermRepositoryProtocol(Protocol):
    """Protocol for long-term repository (enables testing without concrete type)."""

    def get_messages(
        self, session_id: str, limit: int | None = None, offset: int = 0
    ) -> list[MemoryEntry]: ...
    def append_message(self, session_id: str, message: MemoryEntry) -> None: ...
    def clear(self, session_id: str) -> bool: ...
    def close(self) -> None: ...


class MemoryService:
    """
    Memory service implementing cache-aside and write-through patterns with LRU eviction.

    This service coordinates between short-term (Redis) and long-term (PostgreSQL)
    storage, providing efficient message retrieval with automatic caching.

    Design Patterns:
        - Cache-Aside: Lazy-load from DB on cache miss
        - Write-Through: Write to DB then update cache
        - LRU Eviction: Limit in-memory session tracking
    """

    def __init__(
        self,
        short_term_repository: ShortTermRepositoryProtocol,
        long_term_repository: LongTermRepositoryProtocol,
        max_cached_sessions: int = 1000,
    ) -> None:
        """
        Initialize the memory service.

        Args:
            short_term_repository: Redis-based cache
            long_term_repository: PostgreSQL-based persistence
            max_cached_sessions: Maximum sessions to track in LRU cache (prevents memory leak)
        """
        self._short_term_repository = short_term_repository
        self._long_term_repository = long_term_repository
        self._max_cached_sessions = max_cached_sessions
        # LRU cache for tracking which sessions are in Redis (not the actual messages)
        self._session_cache_tracker: OrderedDict[str, bool] = OrderedDict()

    def _track_session_access(self, session_id: str) -> None:
        """
        Track session access for LRU eviction.

        Maintains an LRU cache of session IDs. When max size is exceeded,
        evicts the least recently used session from Redis.
        """
        # Move to end (most recently used)
        if session_id in self._session_cache_tracker:
            self._session_cache_tracker.move_to_end(session_id)
        else:
            self._session_cache_tracker[session_id] = True

            # Evict LRU session if over limit
            if len(self._session_cache_tracker) > self._max_cached_sessions:
                lru_session_id, _ = self._session_cache_tracker.popitem(last=False)
                logger.info(
                    "Evicting LRU session from cache",
                    extra={
                        "evicted_session_id": lru_session_id,
                        "cache_size": len(self._session_cache_tracker),
                    },
                )
                self._short_term_repository.delete_messages(lru_session_id)

    def get_session_state(self, session_id: str) -> SessionState:
        """
        Retrieve session state with cache-aside pattern.

        Flow:
            1. Try to read from cache (Redis)
            2. On cache miss, read from DB
            3. Populate cache with DB data
            4. Track session in LRU

        Args:
            session_id: Unique session identifier

        Returns:
            SessionState with all messages for the session

        Note:
            Redis failures are gracefully handled by falling back to DB.
        """
        # Try cache first (cache-aside pattern)
        cached = self._short_term_repository.get_messages(session_id)
        if cached is not None:
            logger.debug("Cache hit", extra={"session_id": session_id})
            self._track_session_access(session_id)
            return SessionState(session_id=session_id, messages=cached)

        # Cache miss - read from long-term storage
        logger.debug(
            "Cache miss, loading from database", extra={"session_id": session_id}
        )
        try:
            persisted = self._long_term_repository.get_messages(session_id)
        except Exception as e:
            logger.error(
                "Failed to load messages from database",
                extra={"session_id": session_id, "error": str(e)},
            )
            # Return empty state on database error
            return SessionState(session_id=session_id, messages=[])

        # Populate cache for next access
        cache_success = self._short_term_repository.set_messages(session_id, persisted)
        if cache_success:
            self._track_session_access(session_id)
        else:
            logger.warning(
                "Failed to cache messages after DB load",
                extra={"session_id": session_id},
            )

        return SessionState(session_id=session_id, messages=persisted)

    def append_message(self, session_id: str, entry: MemoryEntry) -> None:
        """
        Append a message using write-through pattern.

        Flow:
            1. Write to database (source of truth)
            2. Read back full message list from DB
            3. Update cache with fresh data
            4. Track session in LRU

        Args:
            session_id: Unique session identifier
            entry: Message to append

        Note:
            Database failures will raise exceptions.
            Cache failures are logged but don't fail the operation.
        """
        # Write through to database first (source of truth)
        try:
            self._long_term_repository.append_message(session_id, entry)
        except Exception as e:
            logger.error(
                "Failed to append message to database",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise

        # Read back and update cache
        try:
            refreshed = self._long_term_repository.get_messages(session_id)
            cache_success = self._short_term_repository.set_messages(
                session_id, refreshed
            )
            if cache_success:
                self._track_session_access(session_id)
            else:
                logger.warning(
                    "Failed to update cache after message append",
                    extra={"session_id": session_id},
                )
        except Exception as e:
            logger.error(
                "Failed to refresh cache after append",
                extra={"session_id": session_id, "error": str(e)},
            )
            # Don't fail the operation - message is persisted in DB

    def clear_session(self, session_id: str) -> bool:
        """
        Clear all messages for a session from both cache and database.

        Args:
            session_id: Unique session identifier

        Returns:
            True if messages were cleared from database, False if session didn't exist

        Note:
            Cache is always cleared regardless of database result.
        """
        # Clear from database first
        try:
            cleared = self._long_term_repository.clear(session_id)
        except Exception as e:
            logger.error(
                "Failed to clear messages from database",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise

        # Always clear from cache (even if DB returned False)
        self._short_term_repository.delete_messages(session_id)

        # Remove from LRU tracker
        self._session_cache_tracker.pop(session_id, None)

        return cleared

    def close(self) -> None:
        """
        Close all resources and connections.

        Note:
            Redis connections are managed by the client's connection pool
            and don't need explicit closing.
        """
        try:
            self._long_term_repository.close()
        except Exception as e:
            logger.error(
                "Error while closing long-term repository",
                extra={"error": str(e)},
            )
        finally:
            # Clear the LRU tracker
            self._session_cache_tracker.clear()

    def get_metadata(self, session_id: str, key: str) -> str:
        """
        Retrieve a metadata value for a session.

        Args:
            session_id: Unique session identifier
            key: Metadata key (e.g., "course_code")

        Returns:
            Metadata value as string, or empty string if not found

        Note:
            Metadata is only stored in Redis (short-term), not persisted to database.
        """
        value = self._short_term_repository.get_metadata(session_id, key)
        return value if value is not None else ""

    def set_metadata(self, session_id: str, key: str, value: str) -> None:
        """
        Set a metadata value for a session.

        Args:
            session_id: Unique session identifier
            key: Metadata key (e.g., "course_code")
            value: Metadata value to store

        Note:
            Metadata is only stored in Redis (short-term) with TTL matching session TTL.
            Failures are logged but don't raise exceptions.
        """
        success = self._short_term_repository.set_metadata(session_id, key, value)
        if not success:
            logger.warning(
                "Failed to set session metadata",
                extra={"session_id": session_id, "key": key},
            )

    def delete_metadata(self, session_id: str, key: str) -> None:
        """
        Delete a metadata value for a session.

        Args:
            session_id: Unique session identifier
            key: Metadata key to delete

        Note:
            Failures are logged but don't raise exceptions.
        """
        success = self._short_term_repository.delete_metadata(session_id, key)
        if not success:
            logger.warning(
                "Failed to delete session metadata",
                extra={"session_id": session_id, "key": key},
            )
