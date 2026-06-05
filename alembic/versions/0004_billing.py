"""purchases + paddle_events tables

Revision ID: 0004_billing
Revises: 0003_profile_reads
Create Date: 2026-05-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_billing"
down_revision: Union[str, None] = "0003_profile_reads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ``purchases`` and ``paddle_events`` tables."""
    op.create_table(
        "purchases",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("paddle_transaction_id", sa.String(length=255), nullable=False),
        sa.Column("pack_id", sa.String(length=32), nullable=False),
        sa.Column("hints", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paddle_transaction_id", name="uq_purchases_paddle_txn"),
    )
    op.create_index("ix_purchases_user_id", "purchases", ["user_id"])
    op.create_index("ix_purchases_created_at", "purchases", ["created_at"])
    op.create_index(
        "ix_purchases_paddle_transaction_id", "purchases", ["paddle_transaction_id"]
    )

    op.create_table(
        "paddle_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_paddle_events_event_id"),
    )
    op.create_index("ix_paddle_events_event_id", "paddle_events", ["event_id"])
    op.create_index("ix_paddle_events_created_at", "paddle_events", ["created_at"])


def downgrade() -> None:
    """Drop the ``paddle_events`` and ``purchases`` tables."""
    op.drop_index("ix_paddle_events_created_at", table_name="paddle_events")
    op.drop_index("ix_paddle_events_event_id", table_name="paddle_events")
    op.drop_table("paddle_events")
    op.drop_index("ix_purchases_paddle_transaction_id", table_name="purchases")
    op.drop_index("ix_purchases_created_at", table_name="purchases")
    op.drop_index("ix_purchases_user_id", table_name="purchases")
    op.drop_table("purchases")
