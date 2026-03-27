"""Initial pipeline schema with pgvector.

Revision ID: 001
Revises:
Create Date: 2026-03-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers
revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # courses
    op.create_table(
        "courses",
        sa.Column("course_id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("department", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("prerequisites", ARRAY(sa.Text), nullable=True),
    )

    # documents
    op.create_table(
        "documents",
        sa.Column(
            "doc_id",
            sa.UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "course_id", sa.Text, sa.ForeignKey("courses.course_id"), nullable=True
        ),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column(
            "source_type",
            sa.Text,
            sa.CheckConstraint(
                "source_type IN ('textbook','slides','lecture_notes','exercises')"
            ),
            nullable=True,
        ),
        sa.Column("chapter", sa.Integer, nullable=True),
        sa.Column("chapter_title", sa.Text, nullable=True),
        sa.Column(
            "added_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # chunks
    op.create_table(
        "chunks",
        sa.Column(
            "chunk_id",
            sa.UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("doc_id", sa.UUID, sa.ForeignKey("documents.doc_id"), nullable=True),
        sa.Column(
            "course_id", sa.Text, sa.ForeignKey("courses.course_id"), nullable=True
        ),
        sa.Column("chapter", sa.Integer, nullable=True),
        sa.Column("chapter_title", sa.Text, nullable=True),
        sa.Column("section", sa.Integer, nullable=True),
        sa.Column("section_title", sa.Text, nullable=True),
        sa.Column("chunk_index", sa.Integer, nullable=True),
        sa.Column("element_types", ARRAY(sa.Text), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("keywords", ARRAY(sa.Text), nullable=True),
        sa.Column("questions", ARRAY(sa.Text), nullable=True),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("embedding", sa.Text, nullable=True),  # placeholder — replaced below
        sa.Column(
            "added_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Use raw SQL for vector column (pgvector type not in SA by default)
    op.execute("ALTER TABLE chunks DROP COLUMN embedding")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(1536)")

    # summaries
    op.create_table(
        "summaries",
        sa.Column(
            "summary_id",
            sa.UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "course_id", sa.Text, sa.ForeignKey("courses.course_id"), nullable=True
        ),
        sa.Column(
            "level",
            sa.Text,
            sa.CheckConstraint("level IN ('course','chapter','section')"),
            nullable=True,
        ),
        sa.Column("chapter", sa.Integer, nullable=True),
        sa.Column("chapter_title", sa.Text, nullable=True),
        sa.Column("section", sa.Integer, nullable=True),
        sa.Column("section_title", sa.Text, nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", sa.Text, nullable=True),
    )

    op.execute("ALTER TABLE summaries DROP COLUMN embedding")
    op.execute("ALTER TABLE summaries ADD COLUMN embedding vector(1536)")

    # Unique constraints for idempotent upserts
    op.create_unique_constraint(
        "uq_chunks_course_chapter_section_index",
        "chunks",
        ["course_id", "chapter", "section", "chunk_index"],
    )
    op.create_unique_constraint(
        "uq_summaries_course_level_chapter_section",
        "summaries",
        ["course_id", "level", "chapter", "section"],
    )

    # Indexes
    op.create_index("ix_chunks_course_id", "chunks", ["course_id"])
    op.create_index("ix_chunks_chapter", "chunks", ["chapter"])
    op.execute("CREATE INDEX ix_chunks_keywords ON chunks USING GIN (keywords)")
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON chunks "
        "USING HNSW (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_constraint("uq_summaries_course_level_chapter_section", "summaries")
    op.drop_table("summaries")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_chunks_keywords")
    op.drop_index("ix_chunks_chapter", "chunks")
    op.drop_index("ix_chunks_course_id", "chunks")
    op.drop_constraint("uq_chunks_course_chapter_section_index", "chunks")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("courses")
    op.execute("DROP EXTENSION IF EXISTS vector")
