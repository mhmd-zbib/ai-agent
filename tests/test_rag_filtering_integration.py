"""
Integration tests for course_code filtering in the RAG system.

These tests verify that the RAG service correctly applies Qdrant filters
when querying for documents, ensuring that course_code and university_name
filters work as expected at the vector database level.

Tests mock the Qdrant client's query_points method to simulate various
filtering scenarios without requiring a live Qdrant instance.
"""

import pytest
from unittest.mock import Mock, MagicMock
from qdrant_client.models import ScoredPoint

from app.modules.rag.schemas import SearchQuery
from app.modules.rag.services.rag_service import RAGService
from app.modules.rag.services.base_reranker import BaseReranker
from app.shared.config import RagConfig


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _NoOpReranker(BaseReranker):
    """Reranker that does nothing — returns results as-is."""

    def rerank(self, results):
        return results


@pytest.fixture
def mock_embedding_client():
    """Mock embedding client that returns a fixed vector."""
    client = Mock()
    client.embed.return_value = [0.1, 0.2, 0.3, 0.4]
    return client


@pytest.fixture
def mock_vector_client():
    """Mock vector client for testing Qdrant filtering."""
    client = Mock()
    return client


@pytest.fixture
def rag_service(mock_vector_client, mock_embedding_client):
    """RAG service with mocked dependencies."""
    return RAGService(
        vector_client=mock_vector_client,
        embedding_client=mock_embedding_client,
        reranker=_NoOpReranker(),
        rag_config=RagConfig(),
    )


def _make_scored_point(
    chunk_id: str,
    score: float,
    course_code: str,
    university_name: str = "LIU",
    document_id: str = "doc123",
    text: str = "sample text",
    file_name: str = "sample.pdf",
) -> ScoredPoint:
    """Helper to create a ScoredPoint with metadata."""
    point = Mock(spec=ScoredPoint)
    point.id = chunk_id
    point.score = score
    point.payload = {
        "_chunk_id": chunk_id,
        "chunk_text": text,
        "course_code": course_code,
        "university_name": university_name,
        "document_id": document_id,
        "file_name": file_name,
    }
    return point


def _make_query_response(points: list):
    """Helper to create a query_points response object."""
    response = MagicMock()
    response.points = points
    return response


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_course_code_filter_excludes_other_courses(rag_service, mock_vector_client):
    """
    Test that querying with course_code="PHAR205" only returns PHAR205 chunks,
    excluding chunks from other courses like COMP101.
    """
    # Setup: mock Qdrant to return chunks from different courses
    phar205_chunk = _make_scored_point(
        chunk_id="phar_chunk_1",
        score=0.85,
        course_code="PHAR205",
        text="Pharmacology content",
        document_id="doc_phar",
    )
    comp101_chunk = _make_scored_point(
        chunk_id="comp_chunk_1",
        score=0.75,
        course_code="COMP101",
        text="Computer science content",
        document_id="doc_comp",
    )

    mock_vector_client.query.return_value = [
        {
            "id": phar205_chunk.payload["_chunk_id"],
            "score": phar205_chunk.score,
            "metadata": {
                k: v
                for k, v in phar205_chunk.payload.items()
                if k != "_chunk_id"
            },
        }
    ]

    # Execute: search with course_code filter
    query = SearchQuery(
        text="test query",
        top_k=5,
        user_id="user123",
        course_code="PHAR205",
        university_name="",
    )
    results = rag_service.search(query)

    # Assert: verify filter was applied correctly
    mock_vector_client.query.assert_called_once()
    call_args = mock_vector_client.query.call_args
    assert call_args.kwargs["filter"] == {"course_code": "PHAR205"}
    assert call_args.kwargs["namespace"] == "user123"

    # Assert: only PHAR205 results returned
    assert len(results) == 1
    assert results[0].chunk_id == "phar_chunk_1"
    assert "Pharmacology" in results[0].text


def test_combined_course_and_university_filter(rag_service, mock_vector_client):
    """
    Test that combining course_code and university_name filters
    only returns chunks matching BOTH criteria.
    """
    # Setup: mock Qdrant to return only matching chunks
    matching_chunk = _make_scored_point(
        chunk_id="liu_phar_chunk",
        score=0.90,
        course_code="PHAR205",
        university_name="LIU",
        text="LIU Pharmacology content",
        document_id="doc_liu_phar",
    )

    mock_vector_client.query.return_value = [
        {
            "id": matching_chunk.payload["_chunk_id"],
            "score": matching_chunk.score,
            "metadata": {
                k: v
                for k, v in matching_chunk.payload.items()
                if k != "_chunk_id"
            },
        }
    ]

    # Execute: search with both filters
    query = SearchQuery(
        text="pharmacology question",
        top_k=5,
        user_id="user456",
        course_code="PHAR205",
        university_name="LIU",
    )
    results = rag_service.search(query)

    # Assert: verify both filters were applied
    mock_vector_client.query.assert_called_once()
    call_args = mock_vector_client.query.call_args
    assert call_args.kwargs["filter"] == {
        "course_code": "PHAR205",
        "university_name": "LIU",
    }

    # Assert: only matching results returned
    assert len(results) == 1
    assert results[0].chunk_id == "liu_phar_chunk"
    assert "LIU" in results[0].text


def test_nonexistent_course_returns_empty(rag_service, mock_vector_client):
    """
    Test that querying with a non-existent course code returns an empty list
    without raising an error.
    """
    # Setup: mock Qdrant to return empty results
    mock_vector_client.query.return_value = []

    # Execute: search with non-existent course
    query = SearchQuery(
        text="test query",
        top_k=5,
        user_id="user789",
        course_code="NONEXISTENT999",
        university_name="",
    )
    results = rag_service.search(query)

    # Assert: filter was applied
    mock_vector_client.query.assert_called_once()
    call_args = mock_vector_client.query.call_args
    assert call_args.kwargs["filter"] == {"course_code": "NONEXISTENT999"}

    # Assert: empty list returned (no error)
    assert results == []


def test_empty_course_code_does_not_filter(rag_service, mock_vector_client):
    """
    Test that an empty course_code parameter does not apply filtering,
    allowing results from all courses to be returned.
    """
    # Setup: mock Qdrant to return chunks from multiple courses
    phar_chunk = _make_scored_point(
        chunk_id="phar_chunk",
        score=0.85,
        course_code="PHAR205",
        text="Pharmacology content",
        document_id="doc_phar",
    )
    comp_chunk = _make_scored_point(
        chunk_id="comp_chunk",
        score=0.80,
        course_code="COMP101",
        text="Computer science content",
        document_id="doc_comp",
    )

    mock_vector_client.query.return_value = [
        {
            "id": phar_chunk.payload["_chunk_id"],
            "score": phar_chunk.score,
            "metadata": {
                k: v for k, v in phar_chunk.payload.items() if k != "_chunk_id"
            },
        },
        {
            "id": comp_chunk.payload["_chunk_id"],
            "score": comp_chunk.score,
            "metadata": {
                k: v for k, v in comp_chunk.payload.items() if k != "_chunk_id"
            },
        },
    ]

    # Execute: search with empty course_code
    query = SearchQuery(
        text="general query",
        top_k=5,
        user_id="user_multi",
        course_code="",
        university_name="",
    )
    results = rag_service.search(query)

    # Assert: no filter applied (only namespace)
    mock_vector_client.query.assert_called_once()
    call_args = mock_vector_client.query.call_args
    assert call_args.kwargs["filter"] is None
    assert call_args.kwargs["namespace"] == "user_multi"

    # Assert: results from multiple courses returned
    assert len(results) == 2
    chunk_ids = [r.chunk_id for r in results]
    assert "phar_chunk" in chunk_ids
    assert "comp_chunk" in chunk_ids


def test_filtering_respects_relevance_threshold(rag_service, mock_vector_client):
    """
    Test that filtering still respects the relevance threshold (>= 0.40),
    excluding chunks with low scores even if they match the filter.
    """
    # Setup: mock Qdrant to return chunks with varying scores
    high_score_chunk = _make_scored_point(
        chunk_id="high_score",
        score=0.85,
        course_code="PHAR205",
        text="Highly relevant content",
        document_id="doc_high",
    )
    medium_score_chunk = _make_scored_point(
        chunk_id="medium_score",
        score=0.45,
        course_code="PHAR205",
        text="Somewhat relevant content",
        document_id="doc_medium",
    )
    low_score_chunk = _make_scored_point(
        chunk_id="low_score",
        score=0.25,
        course_code="PHAR205",
        text="Barely relevant content",
        document_id="doc_low",
    )

    mock_vector_client.query.return_value = [
        {
            "id": high_score_chunk.payload["_chunk_id"],
            "score": high_score_chunk.score,
            "metadata": {
                k: v
                for k, v in high_score_chunk.payload.items()
                if k != "_chunk_id"
            },
        },
        {
            "id": medium_score_chunk.payload["_chunk_id"],
            "score": medium_score_chunk.score,
            "metadata": {
                k: v
                for k, v in medium_score_chunk.payload.items()
                if k != "_chunk_id"
            },
        },
        {
            "id": low_score_chunk.payload["_chunk_id"],
            "score": low_score_chunk.score,
            "metadata": {
                k: v
                for k, v in low_score_chunk.payload.items()
                if k != "_chunk_id"
            },
        },
    ]

    # Execute: search with course filter
    query = SearchQuery(
        text="pharmacology query",
        top_k=10,
        user_id="user_threshold",
        course_code="PHAR205",
        university_name="",
    )
    results = rag_service.search(query)

    # Assert: filter was applied
    mock_vector_client.query.assert_called_once()
    call_args = mock_vector_client.query.call_args
    assert call_args.kwargs["filter"] == {"course_code": "PHAR205"}

    # Assert: only chunks with score >= 0.40 are returned
    assert len(results) == 2
    chunk_ids = [r.chunk_id for r in results]
    assert "high_score" in chunk_ids
    assert "medium_score" in chunk_ids
    assert "low_score" not in chunk_ids

    # Assert: scores are correct
    for result in results:
        assert result.score >= 0.40


def test_filter_structure_passed_to_qdrant(rag_service, mock_vector_client):
    """
    Test that the filter dictionary passed to Qdrant has the correct structure
    and contains only non-empty filter values.
    """
    # Setup: mock empty response
    mock_vector_client.query.return_value = []

    # Test case 1: Only course_code provided
    query1 = SearchQuery(
        text="test",
        user_id="user1",
        course_code="PHAR205",
        university_name="",
    )
    rag_service.search(query1)
    call_args1 = mock_vector_client.query.call_args
    assert call_args1.kwargs["filter"] == {"course_code": "PHAR205"}

    # Test case 2: Only university_name provided
    mock_vector_client.reset_mock()
    query2 = SearchQuery(
        text="test",
        user_id="user2",
        course_code="",
        university_name="AUB",
    )
    rag_service.search(query2)
    call_args2 = mock_vector_client.query.call_args
    assert call_args2.kwargs["filter"] == {"university_name": "AUB"}

    # Test case 3: Both filters provided
    mock_vector_client.reset_mock()
    query3 = SearchQuery(
        text="test",
        user_id="user3",
        course_code="COMP101",
        university_name="LAU",
    )
    rag_service.search(query3)
    call_args3 = mock_vector_client.query.call_args
    assert call_args3.kwargs["filter"] == {
        "course_code": "COMP101",
        "university_name": "LAU",
    }

    # Test case 4: No filters provided
    mock_vector_client.reset_mock()
    query4 = SearchQuery(
        text="test",
        user_id="user4",
        course_code="",
        university_name="",
    )
    rag_service.search(query4)
    call_args4 = mock_vector_client.query.call_args
    assert call_args4.kwargs["filter"] is None


def test_namespace_always_applied(rag_service, mock_vector_client):
    """
    Test that the user_id namespace is always applied to queries,
    even when other filters are absent.
    """
    # Setup: mock empty response
    mock_vector_client.query.return_value = []

    # Execute: search with user_id but no other filters
    query = SearchQuery(
        text="test query",
        top_k=5,
        user_id="isolated_user_123",
        course_code="",
        university_name="",
    )
    rag_service.search(query)

    # Assert: namespace (user_id) was applied
    mock_vector_client.query.assert_called_once()
    call_args = mock_vector_client.query.call_args
    assert call_args.kwargs["namespace"] == "isolated_user_123"
    assert call_args.kwargs["filter"] is None


def test_over_fetching_for_diversity(rag_service, mock_vector_client):
    """
    Test that the service over-fetches results (top_k * 4) from Qdrant
    to allow for diversity filtering across multiple documents.
    """
    # Setup: mock empty response
    mock_vector_client.query.return_value = []

    # Execute: search with top_k=5
    query = SearchQuery(
        text="test query",
        top_k=5,
        user_id="user_diversity",
        course_code="PHAR205",
    )
    rag_service.search(query)

    # Assert: fetch_k = top_k * 4 (5 * 4 = 20)
    mock_vector_client.query.assert_called_once()
    call_args = mock_vector_client.query.call_args
    assert call_args.kwargs["top_k"] == 20


def test_diversify_round_robin_across_documents(rag_service, mock_vector_client):
    """
    Test that the diversity filtering distributes chunks across multiple documents
    in round-robin fashion, ensuring every document gets representation.
    """
    # Setup: mock Qdrant to return chunks from 3 different documents
    # All from PHAR205 but different document_ids
    chunks = [
        # Doc A - highest scores
        _make_scored_point(
            "doc_a_chunk_1", 0.95, "PHAR205", document_id="doc_a", text="A1"
        ),
        _make_scored_point(
            "doc_a_chunk_2", 0.94, "PHAR205", document_id="doc_a", text="A2"
        ),
        _make_scored_point(
            "doc_a_chunk_3", 0.93, "PHAR205", document_id="doc_a", text="A3"
        ),
        # Doc B - medium scores
        _make_scored_point(
            "doc_b_chunk_1", 0.85, "PHAR205", document_id="doc_b", text="B1"
        ),
        _make_scored_point(
            "doc_b_chunk_2", 0.84, "PHAR205", document_id="doc_b", text="B2"
        ),
        # Doc C - lower scores but still relevant
        _make_scored_point(
            "doc_c_chunk_1", 0.75, "PHAR205", document_id="doc_c", text="C1"
        ),
        _make_scored_point(
            "doc_c_chunk_2", 0.74, "PHAR205", document_id="doc_c", text="C2"
        ),
    ]

    mock_vector_client.query.return_value = [
        {
            "id": chunk.payload["_chunk_id"],
            "score": chunk.score,
            "metadata": {
                k: v for k, v in chunk.payload.items() if k != "_chunk_id"
            },
        }
        for chunk in chunks
    ]

    # Execute: search with top_k=6
    query = SearchQuery(
        text="pharmacology",
        top_k=6,
        user_id="user_diverse",
        course_code="PHAR205",
    )
    results = rag_service.search(query)

    # Assert: results should be round-robin: A1, B1, C1, A2, B2, C2
    assert len(results) == 6
    expected_order = [
        "doc_a_chunk_1",
        "doc_b_chunk_1",
        "doc_c_chunk_1",
        "doc_a_chunk_2",
        "doc_b_chunk_2",
        "doc_c_chunk_2",
    ]
    actual_order = [r.chunk_id for r in results]
    assert actual_order == expected_order

    # Assert: each document is represented
    doc_ids = [r.document_id for r in results]
    assert "doc_a" in doc_ids
    assert "doc_b" in doc_ids
    assert "doc_c" in doc_ids
