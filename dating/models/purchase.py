"""The ``purchases`` table — one row per hint-pack purchase.

``paddle_transaction_id`` is unique: it's the idempotency key that stops a
re-delivered webhook from granting the same hints twice.
"""

from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from dating.models.base import Base
from dating.utils.datetime import utcnow

# Purchase lifecycle states.
PURCHASE_PENDING = "pending"
PURCHASE_COMPLETED = "completed"
PURCHASE_REFUNDED = "refunded"


def _new_id() -> str:
    """Generate a compact hex id for a purchase."""
    return uuid4().hex


class Purchase(Base):
    """A hint-pack purchase and the hints it grants on completion."""

    __tablename__ = "purchases"
    __repr_attrs__ = ["id", "user_id", "pack_id", "status"]

    id: Mapped[str] = mapped_column(sa.String(32), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        sa.String(255), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    paddle_transaction_id: Mapped[str] = mapped_column(
        sa.String(255), unique=True, index=True, nullable=False
    )
    pack_id: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    hints: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=PURCHASE_PENDING, server_default=PURCHASE_PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(), nullable=False, index=True, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )
