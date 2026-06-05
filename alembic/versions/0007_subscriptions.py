"""subscriptions + hint_grants + sub balance/fair-use columns

Revision ID: 0007_subscriptions
Revises: 0006_match_messages
Create Date: 2026-06-01

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_subscriptions"
down_revision: Union[str, None] = "0006_match_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create subscriptions + hint_grants and extend users / hint_consumptions."""
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("paddle_subscription_id", sa.String(length=255), nullable=False),
        sa.Column("paddle_customer_id", sa.String(length=255), nullable=True),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("billing_interval", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("hints_per_cycle", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cap", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_unlimited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("current_period_start", sa.DateTime(), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("paid_until", sa.DateTime(), nullable=True),
        sa.Column("last_accrued_at", sa.DateTime(), nullable=True),
        sa.Column("last_granted_period", sa.String(length=64), nullable=True),
        sa.Column("canceled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_subscriptions_paddle_subscription_id",
        "subscriptions",
        ["paddle_subscription_id"],
        unique=True,
    )
    op.create_index(
        "ix_subscriptions_paddle_customer_id", "subscriptions", ["paddle_customer_id"]
    )
    op.create_index("ix_subscriptions_created_at", "subscriptions", ["created_at"])

    op.create_table(
        "hint_grants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("subscription_id", sa.String(length=40), nullable=True),
        sa.Column("period_key", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hint_grants_user_id", "hint_grants", ["user_id"])
    op.create_index("ix_hint_grants_subscription_id", "hint_grants", ["subscription_id"])
    op.create_index("ix_hint_grants_created_at", "hint_grants", ["created_at"])

    # users: new balance bucket + subscription link + fair-use counters.
    op.add_column("users", sa.Column("sub_hints", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("subscription_id", sa.String(length=40), nullable=True))
    op.add_column("users", sa.Column("ultimate_day", sa.Date(), nullable=True))
    op.add_column(
        "users", sa.Column("ultimate_used", sa.Integer(), server_default="0", nullable=False)
    )
    op.create_unique_constraint("uq_users_subscription_id", "users", ["subscription_id"])
    op.create_foreign_key(
        "fk_users_subscription_id",
        "users",
        "subscriptions",
        ["subscription_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Widen the consumption source column for "subscription"/"unlimited".
    op.alter_column(
        "hint_consumptions",
        "source",
        existing_type=sa.String(length=8),
        type_=sa.String(length=16),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Reverse 0007."""
    op.alter_column(
        "hint_consumptions",
        "source",
        existing_type=sa.String(length=16),
        type_=sa.String(length=8),
        existing_nullable=False,
    )
    op.drop_constraint("fk_users_subscription_id", "users", type_="foreignkey")
    op.drop_constraint("uq_users_subscription_id", "users", type_="unique")
    op.drop_column("users", "ultimate_used")
    op.drop_column("users", "ultimate_day")
    op.drop_column("users", "subscription_id")
    op.drop_column("users", "sub_hints")

    op.drop_index("ix_hint_grants_created_at", table_name="hint_grants")
    op.drop_index("ix_hint_grants_subscription_id", table_name="hint_grants")
    op.drop_index("ix_hint_grants_user_id", table_name="hint_grants")
    op.drop_table("hint_grants")

    op.drop_index("ix_subscriptions_created_at", table_name="subscriptions")
    op.drop_index("ix_subscriptions_paddle_customer_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_paddle_subscription_id", table_name="subscriptions")
    op.drop_table("subscriptions")
