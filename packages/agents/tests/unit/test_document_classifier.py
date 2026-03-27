"""
Unit tests for agents.document.tools.classifier — DocumentClassifierTool.

Tests the document classification implementation using pattern matching
and structural analysis to categorize educational documents.
"""

from __future__ import annotations

import json

import pytest

from agents.core.tool import ToolExecutionError
from agents.document.tools.classifier import DocumentClassifierTool


class TestDocumentClassifierTool:
    """Test DocumentClassifierTool functionality."""

    def test_tool_metadata(self) -> None:
        """Tool has correct name, description, and parameters."""
        tool = DocumentClassifierTool()
        
        assert tool.name == "document_classifier"
        assert "category" in tool.description.lower()
        assert tool.parameters["type"] == "object"
        assert "document_id" in tool.parameters["properties"]
        assert "document_id" in tool.parameters["required"]

    def test_classify_textbook_content(self) -> None:
        """Classifies textbook-style content correctly."""
        tool = DocumentClassifierTool()
        
        textbook_content = """
        Chapter 1: Introduction to Data Structures
        
        This chapter provides an introduction to fundamental concepts.
        
        Section 1.1: Overview
        Data structures are essential for organizing information.
        
        Section 1.2: Arrays
        Arrays store elements in contiguous memory locations.
        
        Summary:
        In this chapter we covered the basic concepts of data structures.
        
        References:
        [1] Cormen et al., Introduction to Algorithms
        """
        
        result = tool.run({
            "document_id": "doc123",
            "document_text": textbook_content,
            "title": "Introduction to Data Structures"
        })
        
        parsed = json.loads(result)
        assert parsed["category"] == "textbook"
        assert parsed["confidence"] > 0.5
        assert "reasoning" in parsed

    def test_classify_slides_content(self) -> None:
        """Classifies slide-style content correctly."""
        tool = DocumentClassifierTool()
        
        slides_content = """
        CS101 Lecture Slides
        
        Slide 1: Introduction
        • Key Points
        • Overview of Topics
        
        Slide 2: Main Concepts
        → First concept
        → Second concept
        → Third concept
        
        Slide 3: Summary
        • Remember these key points
        • Review before next class
        """
        
        result = tool.run({
            "document_id": "doc456",
            "document_text": slides_content,
            "title": "Lecture Slides - Week 1"
        })
        
        parsed = json.loads(result)
        assert parsed["category"] == "slides"
        assert parsed["confidence"] > 0.5

    def test_classify_lecture_notes_content(self) -> None:
        """Classifies lecture notes correctly."""
        tool = DocumentClassifierTool()
        
        lecture_content = """
        Lecture Notes - March 27, 2024
        
        Today we covered sorting algorithms.
        
        Note: Remember that quicksort has O(n log n) average case.
        
        Last time we discussed binary search trees.
        
        Important: The midterm will cover all topics from lectures 1-10.
        
        Next time: We'll explore graph algorithms.
        """
        
        result = tool.run({
            "document_id": "doc789",
            "document_text": lecture_content,
            "title": "Lecture 5 Notes"
        })
        
        parsed = json.loads(result)
        assert parsed["category"] == "lecture_notes"
        assert parsed["confidence"] > 0.5

    def test_classify_exercises_content(self) -> None:
        """Classifies exercise/homework content correctly."""
        tool = DocumentClassifierTool()
        
        exercise_content = """
        Homework Assignment 3
        
        Problem 1: Implement a binary search tree.
        
        Question 2: What is the time complexity of insertion?
        
        Exercise 3: Write pseudocode for tree traversal.
        
        Solution to Problem 1:
        class BinaryTree:
            def insert(self, value):
                pass
        
        Quiz next week will cover these topics.
        """
        
        result = tool.run({
            "document_id": "doc101",
            "document_text": exercise_content,
            "title": "Assignment 3"
        })
        
        parsed = json.loads(result)
        assert parsed["category"] == "exercises"
        assert parsed["confidence"] > 0.5

    def test_classify_without_text_uses_title(self) -> None:
        """Falls back to title-based classification when no text provided."""
        tool = DocumentClassifierTool()
        
        result = tool.run({
            "document_id": "doc202",
            "title": "Homework Assignment 5"
        })
        
        parsed = json.loads(result)
        assert parsed["category"] == "exercises"
        assert parsed["confidence"] == 0.5
        assert "title only" in parsed["reasoning"].lower()

    def test_classify_with_slide_title(self) -> None:
        """Classifies based on slide-related title."""
        tool = DocumentClassifierTool()
        
        result = tool.run({
            "document_id": "doc303",
            "title": "Presentation on Machine Learning"
        })
        
        parsed = json.loads(result)
        assert parsed["category"] == "slides"

    def test_classify_with_lecture_title(self) -> None:
        """Classifies based on lecture-related title."""
        tool = DocumentClassifierTool()
        
        result = tool.run({
            "document_id": "doc404",
            "title": "Lecture Notes - Week 3"
        })
        
        parsed = json.loads(result)
        assert parsed["category"] == "lecture_notes"

    def test_classify_without_text_or_title_defaults(self) -> None:
        """Defaults to textbook when no indicators present."""
        tool = DocumentClassifierTool()
        
        result = tool.run({
            "document_id": "doc505"
        })
        
        parsed = json.loads(result)
        assert parsed["category"] == "textbook"
        assert parsed["confidence"] == 0.5

    def test_missing_document_id_raises_error(self) -> None:
        """Raises ToolExecutionError when document_id is missing."""
        tool = DocumentClassifierTool()
        
        with pytest.raises(ToolExecutionError) as exc_info:
            tool.run({})
        
        assert "document_id is required" in str(exc_info.value.reason)

    def test_empty_document_id_raises_error(self) -> None:
        """Raises ToolExecutionError when document_id is empty."""
        tool = DocumentClassifierTool()
        
        with pytest.raises(ToolExecutionError) as exc_info:
            tool.run({"document_id": ""})
        
        assert "document_id is required" in str(exc_info.value.reason)

    def test_classification_with_mixed_indicators(self) -> None:
        """Handles content with mixed type indicators correctly."""
        tool = DocumentClassifierTool()
        
        mixed_content = """
        Chapter 1: Introduction
        
        Slide 1: Overview
        • Key points
        
        Exercise 1: Try this problem
        
        Lecture notes from today's class
        """
        
        result = tool.run({
            "document_id": "doc606",
            "document_text": mixed_content
        })
        
        parsed = json.loads(result)
        # Should classify based on strongest indicators
        assert parsed["category"] in ["textbook", "slides", "lecture_notes", "exercises"]
        assert 0.0 <= parsed["confidence"] <= 1.0

    def test_classification_confidence_scoring(self) -> None:
        """Confidence score reflects pattern strength."""
        tool = DocumentClassifierTool()
        
        # Strong textbook indicators
        strong_textbook = """
        Chapter 1: Introduction
        Chapter 2: Background
        Section 1.1: Overview
        Section 1.2: Details
        Summary and References
        Appendix A: Additional Information
        Bibliography
        Index
        """
        
        result = tool.run({
            "document_id": "doc707",
            "document_text": strong_textbook
        })
        
        parsed = json.loads(result)
        assert parsed["category"] == "textbook"
        # Strong indicators should give reasonable confidence
        assert parsed["confidence"] > 0.6

    def test_title_provides_classification_bonus(self) -> None:
        """Title matching category provides scoring bonus."""
        tool = DocumentClassifierTool()
        
        # Content that would score low for all categories
        # but title should influence to exercises
        content = """
        Problem 1: Do this task.
        Question 2: Answer this.
        Exercise 3: Complete the following.
        """
        
        result = tool.run({
            "document_id": "doc808",
            "document_text": content,
            "title": "Homework Assignment 7"  # Strong exercise title
        })
        
        parsed = json.loads(result)
        # Title should influence classification
        assert parsed["category"] == "exercises"

    def test_get_embedding_text(self) -> None:
        """Tool generates embedding text for semantic search."""
        tool = DocumentClassifierTool()
        
        embedding_text = tool.get_embedding_text()
        
        assert "document_classifier" in embedding_text
        assert "category" in embedding_text.lower()
        assert "document_id" in embedding_text

    def test_get_schema(self) -> None:
        """Tool returns complete JSON schema."""
        tool = DocumentClassifierTool()
        
        schema = tool.get_schema()
        
        assert schema["name"] == "document_classifier"
        assert schema["description"] == tool.description
        assert schema["parameters"] == tool.parameters

    def test_to_openai_tool(self) -> None:
        """Tool converts to OpenAI function calling format."""
        tool = DocumentClassifierTool()
        
        openai_format = tool.to_openai_tool()
        
        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "document_classifier"
        assert "parameters" in openai_format["function"]

    def test_short_lines_boost_slides_score(self) -> None:
        """Many short lines boost slides classification."""
        tool = DocumentClassifierTool()
        
        # Create content with many short lines (bullet point style)
        short_lines_content = "\n".join([
            "Title Slide",
            "• Point 1",
            "• Point 2",
            "• Point 3",
            "Next Slide",
            "→ Item A",
            "→ Item B",
            "→ Item C",
            "Conclusion",
            "• Summary point",
            "• Key takeaway",
        ])
        
        result = tool.run({
            "document_id": "doc909",
            "document_text": short_lines_content
        })
        
        parsed = json.loads(result)
        assert parsed["category"] == "slides"

    def test_reasoning_includes_score_details(self) -> None:
        """Reasoning explains classification with scores."""
        tool = DocumentClassifierTool()
        
        result = tool.run({
            "document_id": "doc1010",
            "document_text": "Chapter 1: Introduction\nSection 1.1: Overview",
            "title": "Textbook Chapter"
        })
        
        parsed = json.loads(result)
        reasoning = parsed["reasoning"]
        
        assert "textbook" in reasoning.lower()
        assert "scores:" in reasoning.lower() or "score" in reasoning.lower()
