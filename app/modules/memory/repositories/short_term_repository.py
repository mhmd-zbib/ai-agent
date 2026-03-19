import json
from datetime import UTC, datetime

from redis import Redis
from redis.exceptions import RedisError

from app.modules.memory.schemas import MemoryEntry


class ShortTermRepository:
    def __init__(self, redis_client: Redis, ttl_seconds: int) -> None:
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(session_id: str) -> str:
        return f"chat:session:{session_id}:messages"

    def get_messages(self, session_id: str) -> list[MemoryEntry] | None:
        try:
            payload = self._redis.get(self._key(session_id))
        except RedisError:
            return None

        if payload is None:
            return None

        raw_items = json.loads(payload)
        return [
            MemoryEntry(
                role=item["role"],
                content=item["content"],
                created_at=datetime.fromisoformat(item["created_at"]),
            )
            for item in raw_items
        ]

    def set_messages(self, session_id: str, messages: list[MemoryEntry]) -> None:
        payload = json.dumps(
            [
                {
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at.astimezone(UTC).isoformat(),
                }
                for message in messages
            ]
        )

        try:
            self._redis.set(self._key(session_id), payload, ex=self._ttl_seconds)
        except RedisError:
            return

    def delete_messages(self, session_id: str) -> None:
        try:
            self._redis.delete(self._key(session_id))
        except RedisError:
            return
