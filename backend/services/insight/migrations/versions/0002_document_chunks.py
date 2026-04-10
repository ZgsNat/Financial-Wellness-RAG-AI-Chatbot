"""document_chunks table for RAG vector store

Revision ID: 0002_document_chunks
Revises: 0001_initial
Create Date: 2026-04-09 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_document_chunks"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ensure pgvector extension is available (pgvector/pgvector:pg16 image required)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        # vector(1024) — BGE-M3 output dimension
        sa.Column("embedding", sa.Text, nullable=True),  # placeholder; real type set via raw SQL below
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Replace placeholder TEXT column with pgvector vector(1024)
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1024) USING NULL;")

    # HNSW index for cosine similarity — better than IVFFlat for real-time inserts
    op.execute(
        """
        CREATE INDEX ix_chunks_embedding ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )

    # Composite index: filter user_id + source_type before vector search
    op.create_index("ix_chunks_user_source", "document_chunks", ["user_id", "source_type"])

    # Unique constraint: (source_id, chunk_index) — enables idempotent upsert
    op.create_unique_constraint(
        "uq_chunks_source_chunk",
        "document_chunks",
        ["source_id", "chunk_index"],
    )


def downgrade() -> None:
    op.drop_table("document_chunks")
