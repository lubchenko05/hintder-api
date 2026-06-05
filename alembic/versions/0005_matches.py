"""drop profile_reads, add matches

Revision ID: 0005_matches
Revises: 0004_billing
Create Date: 2026-05-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_matches"
down_revision: Union[str, None] = "0004_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the unused ``profile_reads`` table and create ``matches``."""
    op.drop_index("ix_profile_reads_created_at", table_name="profile_reads")
    op.drop_index("ix_profile_reads_user_id", table_name="profile_reads")
    op.drop_table("profile_reads")

    op.create_table(
        "matches",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="in_progress", nullable=False),
        sa.Column("picked_style", sa.String(length=32), nullable=True),
        sa.Column("picked_tone", sa.String(length=32), nullable=True),
        sa.Column("analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("conversation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matches_user_id", "matches", ["user_id"])
    op.create_index("ix_matches_updated_at_ms", "matches", ["updated_at_ms"])


def downgrade() -> None:
    """Drop ``matches`` and recreate the ``profile_reads`` table."""
    op.drop_index("ix_matches_updated_at_ms", table_name="matches")
    op.drop_index("ix_matches_user_id", table_name="matches")
    op.drop_table("matches")

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
