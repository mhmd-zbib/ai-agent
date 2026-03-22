"""
Unit tests for RetrievalAgent.

RAGService is faked; all search results are injected via _FakeRagService.
"""
from __future__ import annotations

import pytest

from app.modules.agent.agents.retrieval_agent import RetrievalAgent
from app.modules.agent.schemas.sub_agents import RetrievalInput
from app.modules.rag.schemas import SearchQuery, SearchResult


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRagService:
    def __init__(self, results: list[SearchResult], raise_on_search: bool = False) -> None:
        self._results = results
        self._raise = raise_on_search
        self.last_query: SearchQuery | None = None

    def search(self, query: SearchQuery) -> list[SearchResult]:
        self.last_query = query
        if self._raise:
            raise RuntimeError("connection refused")
        return self._results[: query.top_k]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(chunk_id: str, text: str, score: float = 0.9, source: str = "doc.pdf") -> SearchResult:
    return SearchResult(chunk_id=chunk_id, score=score, text=text, source=source)


def _make_agent(
    results: list[SearchResult] | None = None,
    error: bool = False,
) -> tuple[RetrievalAgent, _FakeRagService]:
    svc = _FakeRagService(results or [], raise_on_search=error)
    agent = RetrievalAgent(rag_service=svc)
    return agent, svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_vector_search_returns_chunks() -> None:
    agent, _ = _make_agent(
        results=[
            _make_result("c1", "Chunk one"),
            _make_result("c2", "Chunk two"),
        ]
    )
    output = agent.run(RetrievalInput(query="test query", strategy="vector"))

    assert len(output.chunks) == 2
    assert output.chunks[0].chunk_id == "c1"
    assert output.chunks[0].text == "Chunk one"
    assert output.chunks[0].source == "doc.pdf"
    assert output.strategy_used == "vector"
    assert output.query_used == "test query"


def test_vector_search_empty_result() -> None:
    agent, _ = _make_agent(results=[])
    output = agent.run(RetrievalInput(query="unknown topic", strategy="vector"))

    assert output.chunks == []
    assert output.strategy_used == "vector"


def test_vector_search_respects_top_k() -> None:
    results = [_make_result(f"c{i}", f"Chunk {i}") for i in range(10)]
    agent, svc = _make_agent(results=results)

    output = agent.run(RetrievalInput(query="query", top_k=3, strategy="vector"))

    assert svc.last_query is not None
    assert svc.last_query.top_k == 3
    assert len(output.chunks) == 3


def test_vector_search_failure_returns_empty_not_raise() -> None:
    agent, _ = _make_agent(error=True)
    # Should not raise; graceful degradation
    output = agent.run(RetrievalInput(query="test", strategy="vector"))

    assert output.chunks == []


def test_keyword_strategy_returns_empty_stub() -> None:
    agent, _ = _make_agent(results=[_make_result("c1", "text")])
    output = agent.run(RetrievalInput(query="test", strategy="keyword"))

    assert output.chunks == []
    assert output.strategy_used == "keyword"


def test_hybrid_strategy_merges_vector_and_keyword() -> None:
    # keyword stub returns empty, vector returns 2 chunks; hybrid = 2
    agent, _ = _make_agent(results=[_make_result("c1", "t1"), _make_result("c2", "t2")])
    output = agent.run(RetrievalInput(query="test", strategy="hybrid", top_k=5))

    assert len(output.chunks) == 2
    assert output.strategy_used == "hybrid"


def test_user_id_passed_to_rag_service() -> None:
    agent, svc = _make_agent(results=[])
    agent.run(RetrievalInput(query="q", user_id="user-99", strategy="vector"))
    assert svc.last_query is not None
    assert svc.last_query.user_id == "user-99"


def test_none_rag_service_returns_empty() -> None:
    agent = RetrievalAgent(rag_service=None)
    output = agent.run(RetrievalInput(query="q", strategy="vector"))
    assert output.chunks == []
