"""
Unit tests for agents.research.agent — RetrievalAgent keyword search.

Tests the keyword search implementation in RetrievalAgent to ensure
it properly handles queries, integrates with RAG service, and falls
back gracefully when services are unavailable.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.orchestrator.schemas import RetrievalInput, RetrievedChunk
from agents.research.agent import RetrievalAgent


class TestRetrievalAgentKeywordSearch:
    """Test RetrievalAgent keyword search functionality."""

    def test_keyword_search_with_no_rag_service(self) -> None:
        """Keyword search returns empty list when RAG service is None."""
        agent = RetrievalAgent(rag_service=None)
        
        input_data = RetrievalInput(
            query="test query",
            strategy="keyword",
            top_k=5,
            user_id="user123",
            course_code="CS101",
            university_name="TestU",
        )
        
        output = agent.run(input_data)
        
        assert output.chunks == []
        assert output.strategy_used == "keyword"
        assert output.query_used == "test query"

    def test_keyword_search_with_results(self) -> None:
        """Keyword search returns results from RAG service."""
        # Mock RAG service
        mock_rag = MagicMock()
        
        # Create mock search results with attributes
        mock_result1 = MagicMock()
        mock_result1.chunk_id = "chunk1"
        mock_result1.score = 0.85
        mock_result1.text = "This is test content"
        mock_result1.source = "doc1.pdf"
        
        mock_result2 = MagicMock()
        mock_result2.chunk_id = "chunk2"
        mock_result2.score = 0.72
        mock_result2.text = "More test content"
        mock_result2.source = "doc2.pdf"
        
        mock_rag.search.return_value = [mock_result1, mock_result2]
        
        agent = RetrievalAgent(rag_service=mock_rag)
        
        input_data = RetrievalInput(
            query="test query",
            strategy="keyword",
            top_k=5,
            user_id="user123",
            course_code="CS101",
            university_name="TestU",
        )
        
        output = agent.run(input_data)
        
        assert len(output.chunks) == 2
        assert output.chunks[0].chunk_id == "chunk1"
        assert output.chunks[0].score == 0.85
        assert output.chunks[0].text == "This is test content"
        assert output.chunks[1].chunk_id == "chunk2"
        assert output.strategy_used == "keyword"
        
        # Verify RAG service was called with correct parameters
        mock_rag.search.assert_called_once()
        call_args = mock_rag.search.call_args[0][0]
        assert call_args.text == "test query"
        assert call_args.top_k == 5
        assert call_args.user_id == "user123"

    def test_keyword_search_handles_exceptions(self) -> None:
        """Keyword search returns empty list when RAG service raises exception."""
        mock_rag = MagicMock()
        mock_rag.search.side_effect = RuntimeError("Search failed")
        
        agent = RetrievalAgent(rag_service=mock_rag)
        
        input_data = RetrievalInput(
            query="test query",
            strategy="keyword",
            top_k=5,
            user_id="user123",
            course_code="CS101",
            university_name="TestU",
        )
        
        # Should not raise, but return empty results
        output = agent.run(input_data)
        
        assert output.chunks == []
        assert output.strategy_used == "keyword"

    def test_hybrid_search_merges_vector_and_keyword(self) -> None:
        """Hybrid strategy merges vector and keyword search results."""
        mock_rag = MagicMock()
        
        # Create diverse mock results
        mock_result1 = MagicMock()
        mock_result1.chunk_id = "chunk1"
        mock_result1.score = 0.9
        mock_result1.text = "Vector result"
        mock_result1.source = "doc1.pdf"
        
        mock_result2 = MagicMock()
        mock_result2.chunk_id = "chunk2"
        mock_result2.score = 0.8
        mock_result2.text = "Keyword result"
        mock_result2.source = "doc2.pdf"
        
        # Same chunk appears in both searches - should deduplicate
        mock_result3 = MagicMock()
        mock_result3.chunk_id = "chunk1"  # Duplicate
        mock_result3.score = 0.75
        mock_result3.text = "Vector result"
        mock_result3.source = "doc1.pdf"
        
        mock_rag.search.return_value = [mock_result1, mock_result2, mock_result3]
        
        agent = RetrievalAgent(rag_service=mock_rag)
        
        input_data = RetrievalInput(
            query="test query",
            strategy="hybrid",
            top_k=5,
            user_id="user123",
            course_code="CS101",
            university_name="TestU",
        )
        
        output = agent.run(input_data)
        
        # Should have deduplicated chunk1
        chunk_ids = [c.chunk_id for c in output.chunks]
        assert chunk_ids.count("chunk1") == 1
        assert "chunk2" in chunk_ids
        assert output.strategy_used == "hybrid"

    def test_vector_search_strategy(self) -> None:
        """Vector strategy uses only vector search."""
        mock_rag = MagicMock()
        
        mock_result = MagicMock()
        mock_result.chunk_id = "chunk1"
        mock_result.score = 0.9
        mock_result.text = "Vector content"
        mock_result.source = "doc1.pdf"
        
        mock_rag.search.return_value = [mock_result]
        
        agent = RetrievalAgent(rag_service=mock_rag)
        
        input_data = RetrievalInput(
            query="test query",
            strategy="vector",
            top_k=5,
            user_id="user123",
            course_code="CS101",
            university_name="TestU",
        )
        
        output = agent.run(input_data)
        
        assert len(output.chunks) == 1
        assert output.chunks[0].chunk_id == "chunk1"
        assert output.strategy_used == "vector"

    def test_keyword_search_with_empty_results(self) -> None:
        """Keyword search handles empty results from RAG service."""
        mock_rag = MagicMock()
        mock_rag.search.return_value = []
        
        agent = RetrievalAgent(rag_service=mock_rag)
        
        input_data = RetrievalInput(
            query="test query",
            strategy="keyword",
            top_k=5,
            user_id="user123",
            course_code="CS101",
            university_name="TestU",
        )
        
        output = agent.run(input_data)
        
        assert output.chunks == []
        assert output.strategy_used == "keyword"

    def test_hybrid_search_limits_to_top_k(self) -> None:
        """Hybrid search respects top_k limit after merging."""
        mock_rag = MagicMock()
        
        # Create more results than top_k
        results = []
        for i in range(10):
            mock_result = MagicMock()
            mock_result.chunk_id = f"chunk{i}"
            mock_result.score = 0.9 - (i * 0.05)
            mock_result.text = f"Content {i}"
            mock_result.source = "doc.pdf"
            results.append(mock_result)
        
        mock_rag.search.return_value = results
        
        agent = RetrievalAgent(rag_service=mock_rag)
        
        input_data = RetrievalInput(
            query="test query",
            strategy="hybrid",
            top_k=3,  # Limit to 3 results
            user_id="user123",
            course_code="CS101",
            university_name="TestU",
        )
        
        output = agent.run(input_data)
        
        # Should return exactly top_k results despite having more
        assert len(output.chunks) == 3
        assert output.strategy_used == "hybrid"
