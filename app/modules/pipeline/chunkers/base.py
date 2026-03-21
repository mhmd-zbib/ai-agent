from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Chunk:
    """A single text chunk produced by a chunker."""

    chunk_id: str
    """Stable, deterministic identifier: ``{document_id}_chunk_{index:06d}``."""

    chunk_index: int
    chunk_text: str
    source_page: int | None = None


class BaseChunker(ABC):
    @abstractmethod
    def chunk(
        self,
        *,
        document_id: str,
        text: str,
        pages: list[str] | None = None,
    ) -> list[Chunk]:
        """
        Split *text* into chunks.

        Args:
            document_id: Used to build deterministic chunk IDs.
            text: Full document text.
            pages: Per-page texts (PDFs only). When provided the chunker may
                   use page boundaries to populate ``source_page``.
        """
