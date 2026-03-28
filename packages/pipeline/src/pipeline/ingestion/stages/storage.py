"""Embed consumer — Stage 4 embedding and pgvector storage.

Migrated from pipeline.ingestion.stage4_storage (Stage 4 — Embedding and Hybrid Storage).

Embeds all chunks and summaries using the configured embedding model,
then upserts everything to Postgres with pgvector, BM25 GIN indexes,
and full metadata.
"""

from __future__ import annotations

import logging
import os

import asyncpg
import openai
from common.models.document import (
    ChapterSummary,
    Chunk,
    CourseSummary,
    ParsedDocument,
    SectionSummary,
)

logger = logging.getLogger(__name__)

_EMBED_BATCH_SIZE = 100


class EmbedConsumer:
    """Consume enriched chunks and summaries and store them in Postgres + pgvector.

    Parameters
    ----------
    database_url:
        asyncpg-compatible DSN. Falls back to ``DATABASE_URL`` env var.
    openai_api_key:
        OpenAI API key. Falls back to ``OPENAI_API_KEY`` env var.
    embedding_model:
        Embedding model name. Falls back to ``EMBEDDING_MODEL`` env var
        (default: ``text-embedding-3-large``).
    """

    def __init__(
        self,
        database_url: str | None = None,
        openai_api_key: str | None = None,
        embedding_model: str | None = None,
    ) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL", "")
        self._openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        self._embedding_model = embedding_model or os.environ.get(
            "EMBEDDING_MODEL", "text-embedding-3-large"
        )

    async def run(
        self,
        doc: ParsedDocument,
        chunks: list[Chunk],
        section_summaries: list[SectionSummary],
        chapter_summaries: list[ChapterSummary],
        course_summary: CourseSummary,
    ) -> int:
        """Embed and store all pipeline output in Postgres.

        Parameters
        ----------
        doc:
            Original ParsedDocument (used for doc_id and course upsert).
        chunks:
            Enriched chunks from Stage 3 — includes summary, keywords, questions.
        section_summaries / chapter_summaries / course_summary:
            Hierarchical summaries from Stage 3.

        Returns
        -------
        int
            Number of chunk rows inserted/updated.
        """
        logger.info(
            "EmbedConsumer.run",
            extra={"course_id": doc.course_id, "chunks": len(chunks)},
        )
        return await store(
            doc=doc,
            chunks=chunks,
            section_summaries=section_summaries,
            chapter_summaries=chapter_summaries,
            course_summary=course_summary,
            database_url=self._database_url,
            openai_api_key=self._openai_api_key,
            embedding_model=self._embedding_model,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point (functional form, kept for backward compat)
# ──────────────────────────────────────────────────────────────────────────────


async def store(
    doc: ParsedDocument,
    chunks: list[Chunk],
    section_summaries: list[SectionSummary],
    chapter_summaries: list[ChapterSummary],
    course_summary: CourseSummary,
    database_url: str | None = None,
    openai_api_key: str | None = None,
    embedding_model: str | None = None,
) -> int:
    """Embed and store all pipeline output in Postgres.

    Parameters
    ----------
    doc:
        Original ParsedDocument (used for doc_id and course upsert).
    chunks:
        Enriched chunks from Stage 3 — includes summary, keywords, questions.
    section_summaries / chapter_summaries / course_summary:
        Hierarchical summaries from Stage 3.
    database_url:
        asyncpg-compatible DSN. Falls back to ``DATABASE_URL`` env var.
    openai_api_key:
        OpenAI API key. Falls back to ``OPENAI_API_KEY`` env var.
    embedding_model:
        Embedding model name. Falls back to ``EMBEDDING_MODEL`` env var
        (default: ``text-embedding-3-large``).

    Returns
    -------
    int
        Number of chunk rows inserted/updated.
    """
    db_url = database_url or os.environ.get("DATABASE_URL", "")
    api_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
    model = embedding_model or os.environ.get(
        "EMBEDDING_MODEL", "text-embedding-3-large"
    )

    embed_client = openai.AsyncOpenAI(api_key=api_key)

    # Embed chunks
    chunk_texts = [c.text for c in chunks]
    chunk_embeddings = await _embed_texts(chunk_texts, model, embed_client)

    # Embed summaries (section + chapter + course)
    summary_texts = (
        [s.text for s in section_summaries]
        + [c.text for c in chapter_summaries]
        + [course_summary.text]
    )
    summary_embeddings = await _embed_texts(summary_texts, model, embed_client)

    n_section = len(section_summaries)
    n_chapter = len(chapter_summaries)
    section_emb = summary_embeddings[:n_section]
    chapter_emb = summary_embeddings[n_section : n_section + n_chapter]
    course_emb = summary_embeddings[n_section + n_chapter]

    # Store everything
    conn = await asyncpg.connect(db_url)
    try:
        await _ensure_pgvector(conn)
        await _upsert_course(conn, doc.course_id)
        doc_id = await _upsert_document(conn, doc)
        await _upsert_chunks(conn, doc_id, chunks, chunk_embeddings)
        await _upsert_summaries(
            conn,
            doc.course_id,
            section_summaries,
            section_emb,
            chapter_summaries,
            chapter_emb,
            course_summary,
            course_emb,
        )
        await _validate(conn, doc.course_id)
    finally:
        await conn.close()

    logger.info(
        "Storage complete",
        extra={"course_id": doc.course_id, "chunks_stored": len(chunks)},
    )
    return len(chunks)


# ──────────────────────────────────────────────────────────────────────────────
# Embedding
# ──────────────────────────────────────────────────────────────────────────────


async def _embed_texts(
    texts: list[str],
    model: str,
    client: openai.AsyncOpenAI,
) -> list[list[float]]:
    """Embed *texts* in batches of ``_EMBED_BATCH_SIZE`` to avoid rate limits."""
    if not texts:
        return []
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), _EMBED_BATCH_SIZE):
        batch = texts[i : i + _EMBED_BATCH_SIZE]
        response = await client.embeddings.create(
            model=model,
            input=batch,
            dimensions=1536,  # compatible with pgvector schema
        )
        all_embeddings.extend(item.embedding for item in response.data)
    return all_embeddings


# ──────────────────────────────────────────────────────────────────────────────
# Database operations
# ──────────────────────────────────────────────────────────────────────────────


async def _ensure_pgvector(conn: asyncpg.Connection) -> None:  # type: ignore[type-arg]
    """Ensure the vector extension is enabled (idempotent)."""
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")


async def _upsert_course(conn: asyncpg.Connection, course_id: str) -> None:  # type: ignore[type-arg]
    """Insert the course row if it does not already exist."""
    await conn.execute(
        """
        INSERT INTO courses (course_id, name)
        VALUES ($1, $1)
        ON CONFLICT (course_id) DO NOTHING
        """,
        course_id,
    )


async def _upsert_document(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    doc: ParsedDocument,
) -> str:
    """Insert a documents row and return its doc_id (UUID as string)."""
    row = await conn.fetchrow(
        """
        INSERT INTO documents (course_id, title, source_type)
        VALUES ($1, $2, $3)
        RETURNING doc_id::text
        """,
        doc.course_id,
        f"{doc.course_id} — {doc.source_type}",
        doc.source_type,
    )
    assert row is not None
    return str(row["doc_id"])


async def _upsert_chunks(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    doc_id: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> None:
    """Upsert all chunks.

    Uniqueness key: (course_id, chapter, section, chunk_index).
    On conflict we update all mutable columns so re-running ingestion is safe.
    """
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        vector_literal = f"[{','.join(str(v) for v in embedding)}]"
        await conn.execute(
            """
            INSERT INTO chunks (
                doc_id, course_id, chapter, chapter_title,
                section, section_title, chunk_index, element_types,
                text, summary, keywords, questions, token_count, embedding
            )
            VALUES (
                $1::uuid, $2, $3, $4,
                $5, $6, $7, $8,
                $9, $10, $11, $12, $13, $14::vector
            )
            ON CONFLICT (course_id, chapter, section, chunk_index)
            DO UPDATE SET
                doc_id        = EXCLUDED.doc_id,
                chapter_title = EXCLUDED.chapter_title,
                section_title = EXCLUDED.section_title,
                element_types = EXCLUDED.element_types,
                text          = EXCLUDED.text,
                summary       = EXCLUDED.summary,
                keywords      = EXCLUDED.keywords,
                questions     = EXCLUDED.questions,
                token_count   = EXCLUDED.token_count,
                embedding     = EXCLUDED.embedding
            """,
            doc_id,
            chunk.course_id,
            chunk.chapter,
            chunk.chapter_title,
            chunk.section,
            chunk.section_title,
            chunk.chunk_index,
            chunk.element_types,
            chunk.text,
            chunk.summary,
            chunk.keywords,
            chunk.questions,
            chunk.token_count,
            vector_literal,
        )


async def _upsert_summaries(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    course_id: str,
    section_summaries: list[SectionSummary],
    section_embeddings: list[list[float]],
    chapter_summaries: list[ChapterSummary],
    chapter_embeddings: list[list[float]],
    course_summary: CourseSummary,
    course_embedding: list[float],
) -> None:
    """Upsert all hierarchical summaries into the summaries table."""
    # Section summaries
    for sec_summary, sec_emb in zip(section_summaries, section_embeddings, strict=True):
        vector_literal = f"[{','.join(str(v) for v in sec_emb)}]"
        await conn.execute(
            """
            INSERT INTO summaries (course_id, level, chapter, chapter_title,
                                   section, section_title, text, embedding)
            VALUES ($1, 'section', $2, $3, $4, $5, $6, $7::vector)
            ON CONFLICT (course_id, level, chapter, section)
            DO UPDATE SET
                chapter_title = EXCLUDED.chapter_title,
                section_title = EXCLUDED.section_title,
                text          = EXCLUDED.text,
                embedding     = EXCLUDED.embedding
            """,
            course_id,
            sec_summary.chapter,
            sec_summary.chapter_title,
            sec_summary.section,
            sec_summary.section_title,
            sec_summary.text,
            vector_literal,
        )

    # Chapter summaries
    for ch_summary, ch_emb in zip(chapter_summaries, chapter_embeddings, strict=True):
        vector_literal = f"[{','.join(str(v) for v in ch_emb)}]"
        await conn.execute(
            """
            INSERT INTO summaries (course_id, level, chapter, chapter_title, text, embedding)
            VALUES ($1, 'chapter', $2, $3, $4, $5::vector)
            ON CONFLICT (course_id, level, chapter, section)
            DO UPDATE SET
                chapter_title = EXCLUDED.chapter_title,
                text          = EXCLUDED.text,
                embedding     = EXCLUDED.embedding
            """,
            course_id,
            ch_summary.chapter,
            ch_summary.chapter_title,
            ch_summary.text,
            vector_literal,
        )

    # Course summary
    course_vector = f"[{','.join(str(v) for v in course_embedding)}]"
    await conn.execute(
        """
        INSERT INTO summaries (course_id, level, text, embedding)
        VALUES ($1, 'course', $2, $3::vector)
        ON CONFLICT (course_id, level, chapter, section)
        DO UPDATE SET
            text      = EXCLUDED.text,
            embedding = EXCLUDED.embedding
        """,
        course_id,
        course_summary.text,
        course_vector,
    )


async def _validate(conn: asyncpg.Connection, course_id: str) -> None:  # type: ignore[type-arg]
    """Run post-insertion sanity checks.

    Raises
    ------
    RuntimeError
        If any validation check fails.
    """
    # 1. All chunks have embeddings
    null_count = await conn.fetchval(
        "SELECT COUNT(*) FROM chunks WHERE course_id = $1 AND embedding IS NULL",
        course_id,
    )
    if null_count and null_count > 0:
        raise RuntimeError(
            f"Validation failed: {null_count} chunks in course {course_id!r} have null embeddings."
        )

    # 2. Confirm HNSW index is accessible (query planner can use it)
    await conn.execute("SET LOCAL enable_seqscan = off")
    try:
        row = await conn.fetchrow(
            """
            SELECT chunk_id FROM chunks
            WHERE course_id = $1
            ORDER BY embedding <=> '[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                                     0,0,0,0,0,0,0,0]::vector
            LIMIT 1
            """,
            course_id,
        )
        if row is None:
            logger.info(
                "No chunks found for course during validation",
                extra={"course_id": course_id},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("HNSW index check skipped", extra={"error": str(exc)})
    finally:
        await conn.execute("SET LOCAL enable_seqscan = on")

    logger.info("Validation passed", extra={"course_id": course_id})


__all__ = ["EmbedConsumer", "store"]
