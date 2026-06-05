"""The ``users`` table — identity (Firebase) plus hint balance counters."""

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from dating.models.base import Base
from dating.utils.datetime import utcnow


class User(Base):
    """A hintder user, keyed by Firebase UID.

    Hint balance lives in THREE counters, drained in this order:
    ``free_hints`` (one-time signup grant) → ``sub_hints`` (recurring
    subscription grants, subject to a rollover cap) → ``paid_hints`` (one-time
    top-ups, never capped, kept for last). The active subscription is pointed at
    by ``subscription_id`` — the FK lives here so a subscription is a standalone,
    re-assignable asset. Ultimate (unlimited) users draw no balance; their daily
    fair-use usage is tracked in ``ultimate_day`` / ``ultimate_used``.
    """

    __tablename__ = "users"
    __repr_attrs__ = ["id", "email"]

    id: Mapped[str] = mapped_column(sa.String(255), primary_key=True)  # Firebase UID
    email: Mapped[str | None] = mapped_column(sa.String(320), unique=True, nullable=True)
    name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    avatar: Mapped[str | None] = mapped_column(sa.String(1024), nullable=True)

    # Hint balance — drained free → sub → paid.
    free_hints: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=3, server_default="3"
    )
    sub_hints: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    paid_hints: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )

    # Current subscription (FK here → subscription is a re-assignable asset).
    subscription_id: Mapped[str | None] = mapped_column(
        sa.String(40),
        sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )

    # Ultimate fair-use: per-day usage counter (resets when the date changes).
    ultimate_day: Mapped[date | None] = mapped_column(sa.Date(), nullable=True)
    ultimate_used: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )

    # Paddle linkage (set on first purchase)
    paddle_customer_id: Mapped[str | None] = mapped_column(
        sa.String(255), nullable=True, index=True
    )

    # Anti-abuse: the device/browser that first created an account here. Free
    # hints are granted once per device, so logging out and bootstrapping a fresh
    # anonymous account on the same device doesn't re-grant them.
    device_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(), nullable=False, index=True, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )

    @property
    def total_hints(self) -> int:
        """Total spendable balance (free + subscription + top-up)."""
        return self.free_hints + self.sub_hints + self.paid_hints
