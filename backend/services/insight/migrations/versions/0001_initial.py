"""initial insight tables

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector extension — needed for phase 2 RAG embeddings.
    # Wrapped in a PL/pgSQL block so the migration succeeds even on a plain
    # postgres:16-alpine image (which ships without the vector shared library).
    # Phase 1 has no vector columns; phase 2 must use pgvector/pgvector:pg16.
    op.execute(
        """
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS vector;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'pgvector not available — skipping. Switch to pgvector/pgvector:pg16 for Phase 2.';
        END
        $$;
        """
    )

    op.create_table(
        "insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("insight_type", sa.String(30), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "insight_type", name="uq_insight_user_type"),
    )
    op.create_index("ix_insights_user_id", "insights", ["user_id"])


def downgrade() -> None:
    op.drop_table("insights")