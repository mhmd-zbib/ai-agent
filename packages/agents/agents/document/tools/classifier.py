"""
agents.document.tools.classifier — DocumentClassifierTool implementation.

Classifies uploaded documents into educational content categories using
structural analysis and content patterns. Supports textbook, slides,
lecture notes, and exercises classification.
"""

from __future__ import annotations

from typing import Any

from agents.core.tool import BaseTool, ToolExecutionError
from shared.logging import get_logger

__all__ = ["DocumentClassifierTool"]

logger = get_logger(__name__)


class DocumentClassifierTool(BaseTool):
    """
    Classifies a document into an educational content category.

    Uses heuristic-based classification analyzing document structure,
    formatting patterns, and content characteristics to determine
    document type. Categories include:
    
    - textbook: Structured chapters, formal explanations, comprehensive
    - slides: Bullet points, concise text, visual heavy
    - lecture_notes: Sequential notes, date stamps, informal
    - exercises: Problems, questions, answer sections

    This implementation uses pattern matching and structural analysis.
    Can be extended with LLM-based classification for higher accuracy.
    """

    name = "document_classifier"
    description = (
        "Classifies a document into a category such as 'textbook', 'slides', "
        "'lecture_notes', or 'exercises' based on its content structure and patterns."
    )
    parameters = {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "The identifier of the document to classify",
            },
            "document_text": {
                "type": "string",
                "description": "Optional document text content for classification. If not provided, will fetch from storage.",
            },
            "title": {
                "type": "string",
                "description": "Optional document title for additional context",
            },
        },
        "required": ["document_id"],
    }

    def __init__(self) -> None:
        """Initialize the document classifier with pattern rules."""
        # Textbook indicators
        self._textbook_patterns = [
            "chapter",
            "section",
            "introduction",
            "summary",
            "references",
            "bibliography",
            "index",
            "appendix",
        ]
        
        # Slides indicators
        self._slides_patterns = [
            "slide",
            "•",
            "→",
            "presentation",
            "overview",
            "key points",
        ]
        
        # Lecture notes indicators
        self._lecture_patterns = [
            "lecture",
            "today",
            "last time",
            "next time",
            "note:",
            "remember:",
            "important:",
        ]
        
        # Exercise indicators
        self._exercise_patterns = [
            "exercise",
            "problem",
            "question",
            "solution",
            "answer",
            "homework",
            "assignment",
            "quiz",
        ]

    def run(self, arguments: dict[str, Any]) -> str:
        """
        Classify the document based on content patterns.

        Args:
            arguments: Dictionary containing document_id and optionally
                      document_text and title.

        Returns:
            JSON string with classification result containing:
            - category: The predicted document type
            - confidence: Classification confidence score (0.0-1.0)
            - reasoning: Explanation of the classification decision

        Raises:
            ToolExecutionError: If classification fails.
        """
        document_id = str(arguments.get("document_id", ""))
        document_text = str(arguments.get("document_text", ""))
        title = str(arguments.get("title", ""))

        if not document_id:
            raise ToolExecutionError(
                tool_id=self.name,
                reason="document_id is required",
                user_message="Document ID must be provided for classification.",
            )

        try:
            # If no text provided, return a placeholder response
            if not document_text:
                logger.warning(
                    "Document classifier: no text provided, using title only",
                    extra={"document_id": document_id},
                )
                # Use title-based classification as fallback
                if title:
                    category = self._classify_from_title(title)
                else:
                    category = "textbook"  # Default fallback
                
                return (
                    f'{{"category": "{category}", '
                    f'"confidence": 0.5, '
                    f'"reasoning": "Classification based on title only. Provide document_text for better accuracy."}}'
                )

            # Perform full classification
            category, confidence, reasoning = self._classify_content(
                document_text, title
            )

            logger.info(
                "Document classified",
                extra={
                    "document_id": document_id,
                    "category": category,
                    "confidence": confidence,
                },
            )

            return (
                f'{{"category": "{category}", '
                f'"confidence": {confidence:.2f}, '
                f'"reasoning": "{reasoning}"}}'
            )

        except Exception as exc:
            logger.error(
                "Document classification failed",
                extra={"document_id": document_id, "error": str(exc)},
            )
            raise ToolExecutionError(
                tool_id=self.name,
                reason=str(exc),
                user_message=f"Failed to classify document '{document_id}': {exc}",
            ) from exc

    def _classify_from_title(self, title: str) -> str:
        """Classify based on title keywords."""
        title_lower = title.lower()
        
        if any(p in title_lower for p in ["slide", "presentation"]):
            return "slides"
        if any(p in title_lower for p in ["lecture", "notes"]):
            return "lecture_notes"
        if any(p in title_lower for p in ["exercise", "homework", "assignment", "quiz"]):
            return "exercises"
        
        return "textbook"

    def _classify_content(
        self, text: str, title: str
    ) -> tuple[str, float, str]:
        """
        Classify document based on content analysis.

        Returns:
            Tuple of (category, confidence, reasoning)
        """
        text_lower = text.lower()
        
        # Count pattern matches for each category
        textbook_score = sum(
            text_lower.count(p) for p in self._textbook_patterns
        )
        slides_score = sum(
            text_lower.count(p) for p in self._slides_patterns
        )
        lecture_score = sum(
            text_lower.count(p) for p in self._lecture_patterns
        )
        exercise_score = sum(
            text_lower.count(p) for p in self._exercise_patterns
        )

        # Analyze text structure
        lines = text.split("\n")
        non_empty_lines = [line for line in lines if line.strip()]
        short_lines = sum(1 for line in non_empty_lines if len(line.strip()) < 50)
        
        # Boost slides score if many short lines (bullet points)
        if len(non_empty_lines) > 0 and short_lines / len(non_empty_lines) > 0.5:
            slides_score += 5

        # Determine winner
        scores = {
            "textbook": textbook_score,
            "slides": slides_score,
            "lecture_notes": lecture_score,
            "exercises": exercise_score,
        }
        
        # Add title-based bonus (stronger weight for title)
        if title:
            title_category = self._classify_from_title(title)
            scores[title_category] += 5  # Increased from 3 to 5

        max_score = max(scores.values())
        if max_score == 0:
            # No clear indicators, default to textbook
            return "textbook", 0.5, "No clear indicators found, defaulting to textbook"

        category = max(scores, key=scores.get)  # type: ignore[arg-type]
        
        # Calculate confidence based on score separation
        sorted_scores = sorted(scores.values(), reverse=True)
        top_score = sorted_scores[0]
        second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0
        
        # Confidence based on how much the winner dominates
        if second_score == 0:
            confidence = 0.95
        else:
            # Larger gap = higher confidence
            gap_ratio = (top_score - second_score) / top_score
            confidence = min(0.95, 0.5 + (gap_ratio * 0.45))

        # Build reasoning
        top_patterns = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:2]
        reasoning = (
            f"Classified as {category} based on content patterns. "
            f"Scores: {top_patterns[0][0]}={top_patterns[0][1]}, "
            f"{top_patterns[1][0]}={top_patterns[1][1]}"
        )

        return category, confidence, reasoning
