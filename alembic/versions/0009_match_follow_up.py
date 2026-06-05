"""add follow_up column to matches

Revision ID: 0009_match_follow_up
Revises: 0008_scheduled_plan_changes
Create Date: 2026-06-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_match_follow_up"
down_revision: Union[str, None] = "0008_scheduled_plan_changes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable ``follow_up`` JSONB holding a match's last reply read."""
    op.add_column(
        "matches",
        sa.Column("follow_up", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Drop the ``follow_up`` column."""
    op.drop_column("matches", "follow_up")
