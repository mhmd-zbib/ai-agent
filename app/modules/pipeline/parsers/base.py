import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedDocument:
    """Output of any parser."""

    text: str
    """Cleaned, concatenated text ready for chunking."""

    pages: list[str] | None = field(default=None)
    """Per-page text for PDFs; None for formats without page concept."""


def clean_text(text: str) -> str:
    """Remove excessive whitespace while preserving paragraph breaks."""
    # Collapse runs of spaces / tabs to a single space
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse 3+ consecutive newlines to two (preserve paragraph breaks)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class BaseParser(ABC):
    @abstractmethod
    def parse(self, content: bytes, file_name: str = "") -> ParsedDocument:
        """Parse raw bytes and return a :class:`ParsedDocument`."""
