"""add users.device_id for per-device free-hint grants

Revision ID: 0010_user_device_id
Revises: d3bb27a6b918
Create Date: 2026-06-05 14:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0010_user_device_id"
down_revision: Union[str, None] = "d3bb27a6b918"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("device_id", sa.String(length=64), nullable=True))
    op.create_index("ix_users_device_id", "users", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_users_device_id", table_name="users")
    op.drop_column("users", "device_id")
