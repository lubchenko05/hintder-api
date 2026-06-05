"""profile_reads table

Revision ID: 0003_profile_reads
Revises: 0002_hint_consumptions
Create Date: 2026-05-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_profile_reads"
down_revision: Union[str, None] = "0002_hint_consumptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ``profile_reads`` table (persisted reads + openers)."""
    op.create_table(
        "profile_reads",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("match_label", sa.String(length=120), nullable=True),
        sa.Column("tone", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("hooks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("openers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profile_reads_user_id", "profile_reads", ["user_id"])
    op.create_index("ix_profile_reads_created_at", "profile_reads", ["created_at"])


def downgrade() -> None:
    """Drop the ``profile_reads`` table and its indexes."""
    op.drop_index("ix_profile_reads_created_at", table_name="profile_reads")
    op.drop_index("ix_profile_reads_user_id", table_name="profile_reads")
    op.drop_table("profile_reads")
