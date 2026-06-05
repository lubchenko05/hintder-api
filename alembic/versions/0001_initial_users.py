"""initial users table

Revision ID: 0001_initial_users
Revises:
Create Date: 2026-05-29

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_users"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ``users`` table with identity + hint-balance columns."""
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("avatar", sa.String(length=1024), nullable=True),
        sa.Column("free_hints", sa.Integer(), server_default="3", nullable=False),
        sa.Column("paid_hints", sa.Integer(), server_default="0", nullable=False),
        sa.Column("paddle_customer_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_created_at", "users", ["created_at"])
    op.create_index("ix_users_paddle_customer_id", "users", ["paddle_customer_id"])


def downgrade() -> None:
    """Drop the ``users`` table and its indexes."""
    op.drop_index("ix_users_paddle_customer_id", table_name="users")
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_table("users")
