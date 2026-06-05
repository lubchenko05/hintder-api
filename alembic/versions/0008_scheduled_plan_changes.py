"""scheduled plan changes on subscription

Revision ID: 0008_scheduled_plan_changes
Revises: 0007_subscriptions
Create Date: 2026-06-01

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0008_scheduled_plan_changes"
down_revision: Union[str, None] = "0007_subscriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add scheduled_plan_id and cancel_at_period_end to subscriptions."""
    op.add_column(
        "subscriptions",
        sa.Column("scheduled_plan_id", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Remove scheduled change columns."""
    op.drop_column("subscriptions", "cancel_at_period_end")
    op.drop_column("subscriptions", "scheduled_plan_id")
