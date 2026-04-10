"""Phase 3 — Hybrid search: add fts (full-text search) column + GIN index

Adds a GENERATED tsvector column on document_chunks.content so that
BM25-style lexical scoring via ts_rank() can be combined with pgvector
cosine similarity for hybrid retrieval.

Revision ID: 0003_hybrid_fts
Revises: 0002_document_chunks
Create Date: 2026-04-09 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003_hybrid_fts"
down_revision: str | None = "0002_document_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add GENERATED ALWAYS tsvector column — auto-updated on INSERT/UPDATE
    # Using 'simple' dictionary: no language stemming, works for Vietnamese + English.
    # 'pg_catalog.simple' tokenises by whitespace only, preserving Vietnamese words.
    op.execute(
        """
        ALTER TABLE document_chunks
          ADD COLUMN fts tsvector
            GENERATED ALWAYS AS (to_tsvector('pg_catalog.simple', content)) STORED;
        """
    )

    # GIN index — required for ts_rank() performance over large corpora
    op.execute(
        "CREATE INDEX ix_chunks_fts ON document_chunks USING GIN(fts);"
    )

    # Back-fill: existing rows already have fts set via GENERATED ALWAYS,
    # but we VACUUM ANALYZE to let the planner pick up the new index.
    op.execute("ANALYZE document_chunks;")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_fts;")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS fts;")
