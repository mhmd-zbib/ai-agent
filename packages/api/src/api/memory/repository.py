import json
from datetime import UTC, datetime
from typing import Any, cast

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError
from common.core.log_config import get_logger
from common.core.schemas import MemoryEntry
from api.db.tables import chat_messages
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError

logger = get_logger(__name__)


class ShortTermRepository:
    """Redis-based repository for short-term message caching with automatic TTL."""

    def __init__(self, redis_client: Redis, ttl_seconds: int) -> None:
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(session_id: str) -> str:
        return f"chat:session:{session_id}:messages"

    def _serialize_message(self, message: MemoryEntry) -> dict[str, str]:
        return {
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.astimezone(UTC).isoformat(),
        }

    def _deserialize_message(self, data: dict[str, Any]) -> MemoryEntry:
        return MemoryEntry(
            role=data["role"],
            content=data["content"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def get_messages(self, session_id: str) -> list[MemoryEntry] | None:
        try:
            payload = self._redis.get(self._key(session_id))
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during get",
                extra={"session_id": session_id, "error": str(e)},
            )
            return None
        except RedisError as e:
            logger.error(
                "Redis error during get_messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            return None

        if payload is None:
            return None

        try:
            raw_items: list[dict[str, Any]] = json.loads(payload)
            return [self._deserialize_message(item) for item in raw_items]
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(
                "Failed to deserialize cached messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            self._safe_delete(session_id)
            return None

    def set_messages(self, session_id: str, messages: list[MemoryEntry]) -> bool:
        try:
            payload = json.dumps([self._serialize_message(msg) for msg in messages])
        except (TypeError, ValueError) as e:
            logger.error(
                "Failed to serialize messages for caching",
                extra={"session_id": session_id, "error": str(e)},
            )
            return False

        try:
            self._redis.set(self._key(session_id), payload, ex=self._ttl_seconds)
            return True
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during set",
                extra={"session_id": session_id, "error": str(e)},
            )
            return False
        except RedisError as e:
            logger.error(
                "Redis error during set_messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            return False

    def delete_messages(self, session_id: str) -> bool:
        return self._safe_delete(session_id)

    def _safe_delete(self, session_id: str) -> bool:
        try:
            self._redis.delete(self._key(session_id))
            return True
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during delete",
                extra={"session_id": session_id, "error": str(e)},
            )
            return False
        except RedisError as e:
            logger.error(
                "Redis error during delete_messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            return False

    @staticmethod
    def _metadata_key(session_id: str, key: str) -> str:
        return f"chat:session:{session_id}:metadata:{key}"

    def get_metadata(self, session_id: str, key: str) -> str | None:
        try:
            value = self._redis.get(self._metadata_key(session_id, key))
            return value if value else None
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during get_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return None
        except RedisError as e:
            logger.error(
                "Redis error during get_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return None

    def set_metadata(self, session_id: str, key: str, value: str) -> bool:
        try:
            self._redis.set(
                self._metadata_key(session_id, key), value, ex=self._ttl_seconds
            )
            return True
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during set_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return False
        except RedisError as e:
            logger.error(
                "Redis error during set_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return False

    def delete_metadata(self, session_id: str, key: str) -> bool:
        try:
            self._redis.delete(self._metadata_key(session_id, key))
            return True
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during delete_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return False
        except RedisError as e:
            logger.error(
                "Redis error during delete_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return False


class LongTermRepository:
    """PostgreSQL-based repository for long-term message persistence."""

    def __init__(self, engine: Engine, query_timeout_seconds: int = 30) -> None:
        self._engine = engine
        self._query_timeout_seconds = query_timeout_seconds

    def ensure_schema(self) -> None:
        with self._engine.begin() as conn:
            chat_messages.create(conn, checkfirst=True)

    def get_messages(
        self,
        session_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        stmt = (
            select(
                chat_messages.c.role,
                chat_messages.c.content,
                chat_messages.c.created_at,
            )
            .where(chat_messages.c.session_id == session_id)
            .order_by(chat_messages.c.message_index.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)

        try:
            with self._engine.connect() as conn:
                conn.execute(
                    text(f"SET LOCAL statement_timeout = '{self._query_timeout_seconds}s'")
                )
                rows = conn.execute(stmt).mappings()
                return [
                    MemoryEntry(
                        role=cast(str, row["role"]),
                        content=str(row["content"]),
                        created_at=row["created_at"] or datetime.now(UTC),
                    )
                    for row in rows
                ]
        except TimeoutError as e:
            logger.error(
                "Database query timeout while fetching messages",
                extra={
                    "session_id": session_id,
                    "timeout_seconds": self._query_timeout_seconds,
                    "error": str(e),
                },
            )
            raise
        except OperationalError as e:
            logger.error(
                "Database operational error while fetching messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise
        except DBAPIError as e:
            logger.error(
                "Database error while fetching messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise

    def get_message_count(self, session_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(chat_messages)
            .where(chat_messages.c.session_id == session_id)
        )
        try:
            with self._engine.connect() as conn:
                conn.execute(
                    text(f"SET LOCAL statement_timeout = '{self._query_timeout_seconds}s'")
                )
                return int(conn.execute(stmt).scalar_one())
        except (TimeoutError, OperationalError, DBAPIError) as e:
            logger.error(
                "Database error while counting messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise

    def append_message(self, session_id: str, message: MemoryEntry) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(f"SET LOCAL statement_timeout = '{self._query_timeout_seconds}s'")
                )
                # Advisory lock prevents race conditions on next-index calculation
                conn.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:session_id))"),
                    {"session_id": session_id},
                )
                next_index = int(
                    conn.execute(
                        select(
                            func.coalesce(func.max(chat_messages.c.message_index), -1)
                        ).where(chat_messages.c.session_id == session_id)
                    ).scalar_one()
                ) + 1

                conn.execute(
                    chat_messages.insert().values(
                        session_id=session_id,
                        message_index=next_index,
                        role=message.role,
                        content=message.content,
                        created_at=message.created_at,
                    )
                )
        except TimeoutError as e:
            logger.error(
                "Database query timeout while appending message",
                extra={
                    "session_id": session_id,
                    "timeout_seconds": self._query_timeout_seconds,
                    "error": str(e),
                },
            )
            raise
        except (OperationalError, DBAPIError) as e:
            logger.error(
                "Database error while appending message",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise

    def clear(self, session_id: str) -> bool:
        stmt = delete(chat_messages).where(chat_messages.c.session_id == session_id)
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(f"SET LOCAL statement_timeout = '{self._query_timeout_seconds}s'")
                )
                result = conn.execute(stmt)
                return result.rowcount > 0
        except (TimeoutError, OperationalError, DBAPIError) as e:
            logger.error(
                "Database error while clearing messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise

    def close(self) -> None:
        try:
            self._engine.dispose()
        except Exception as e:
            logger.error("Error while disposing database engine", extra={"error": str(e)})
