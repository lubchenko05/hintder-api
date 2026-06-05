"""hint_consumptions ledger

Revision ID: 0002_hint_consumptions
Revises: 0001_initial_users
Create Date: 2026-05-29

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_hint_consumptions"
down_revision: Union[str, None] = "0001_initial_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the append-only ``hint_consumptions`` ledger table."""
    op.create_table(
        "hint_consumptions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("reference_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_hint_consumptions_user_id", "hint_consumptions", ["user_id"]
    )
    op.create_index(
        "ix_hint_consumptions_created_at", "hint_consumptions", ["created_at"]
    )


def downgrade() -> None:
    """Drop the ``hint_consumptions`` table and its indexes."""
    op.drop_index("ix_hint_consumptions_created_at", table_name="hint_consumptions")
    op.drop_index("ix_hint_consumptions_user_id", table_name="hint_consumptions")
    op.drop_table("hint_consumptions")
