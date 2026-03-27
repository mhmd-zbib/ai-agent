"""Chunk consumer — Stage 2 structure-aware chunking.

Wraps :func:`~ingestion.transforms.chunker.chunk_document` in a consumer
interface consistent with :class:`~ingestion.consumers.ingest.IngestConsumer`
and :class:`~ingestion.consumers.embed.EmbedConsumer`.
"""

from __future__ import annotations

import logging

from shared.models.document import Chunk, ParsedDocument

from ingestion.transforms.chunker import chunk_document

logger = logging.getLogger(__name__)


class ChunkConsumer:
    """Consume a :class:`ParsedDocument` and produce a flat list of :class:`Chunk` objects.

    Delegates entirely to :func:`~ingestion.transforms.chunker.chunk_document`.
    The consumer layer exists so this stage can be composed with the others
    without the orchestrator needing to know the transform internals.
    """

    def run(self, doc: ParsedDocument) -> list[Chunk]:
        """Split *doc* into a list of :class:`Chunk` objects.

        Parameters
        ----------
        doc:
            Fully parsed document from Stage 1 (:class:`IngestConsumer`).

        Returns
        -------
        list[Chunk]
            Ordered chunks ready for Stage 3 metadata generation.
        """
        logger.info(
            "ChunkConsumer.run",
            extra={"course_id": doc.course_id, "chapters": len(doc.chapters)},
        )
        return chunk_document(doc)


__all__ = ["ChunkConsumer"]
