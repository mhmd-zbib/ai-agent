from app.modules.memory.schemas import MemoryEntry
from app.modules.memory.services.memory_service import MemoryService


class FakeShortTermRepository:
    def __init__(self) -> None:
        self._store: dict[str, list[MemoryEntry]] = {}

    def get_messages(self, session_id: str):
        return self._store.get(session_id)

    def set_messages(self, session_id: str, messages: list[MemoryEntry]) -> None:
        self._store[session_id] = list(messages)

    def delete_messages(self, session_id: str) -> None:
        self._store.pop(session_id, None)


class FakeLongTermRepository:
    def __init__(self) -> None:
        self._store: dict[str, list[MemoryEntry]] = {}
        self.get_calls = 0

    def get_messages(self, session_id: str) -> list[MemoryEntry]:
        self.get_calls += 1
        return list(self._store.get(session_id, []))

    def append_message(self, session_id: str, message: MemoryEntry) -> None:
        self._store.setdefault(session_id, []).append(message)

    def clear(self, session_id: str) -> bool:
        return self._store.pop(session_id, None) is not None

    def close(self) -> None:
        return


def test_get_messages_reads_through_cache() -> None:
    short_term = FakeShortTermRepository()
    long_term = FakeLongTermRepository()
    service = MemoryService(
        short_term_repository=short_term,  # type: ignore[arg-type]
        long_term_repository=long_term,  # type: ignore[arg-type]
    )

    long_term.append_message("session-1", MemoryEntry(role="user", content="hello"))

    first = service.get_session_state("session-1")
    second = service.get_session_state("session-1")

    assert len(first.messages) == 1
    assert len(second.messages) == 1
    assert long_term.get_calls == 1


def test_clear_removes_messages_from_source_and_cache() -> None:
    short_term = FakeShortTermRepository()
    long_term = FakeLongTermRepository()
    service = MemoryService(
        short_term_repository=short_term,  # type: ignore[arg-type]
        long_term_repository=long_term,  # type: ignore[arg-type]
    )

    long_term.append_message("session-2", MemoryEntry(role="user", content="hello"))
    service.get_session_state("session-2")

    assert service.clear_session("session-2") is True
    assert service.get_session_state("session-2").messages == []
