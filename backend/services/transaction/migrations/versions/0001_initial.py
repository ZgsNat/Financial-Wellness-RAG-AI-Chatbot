"""initial transactions table

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
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="VND"),
        sa.Column("type", sa.String(10), nullable=False, server_default="expense"),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_transactions_user_date", "transactions", ["user_id", "transaction_date"])


def downgrade() -> None:
    op.drop_index("ix_transactions_user_date", table_name="transactions")
    op.drop_table("transactions")