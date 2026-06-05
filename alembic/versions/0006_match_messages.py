"""add messages column to matches

Revision ID: 0006_match_messages
Revises: d8efb96904f2
Create Date: 2026-06-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_match_messages"
down_revision: Union[str, None] = "d8efb96904f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the ``messages`` JSONB column holding a match's paid openers."""
    op.add_column(
        "matches",
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    """Drop the ``messages`` column."""
    op.drop_column("matches", "messages")
