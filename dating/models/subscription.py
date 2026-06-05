"""The ``subscriptions`` table — a recurring plan as an independent asset.

A subscription is deliberately NOT owned via a column here; instead the user
points at it (``users.subscription_id`` FK). That makes the subscription a
standalone, transferable object: support can re-point it to another user (e.g.
when someone loses access to an anonymous account) without touching the row or
the Paddle record. The current owner is found by the reverse lookup
``User WHERE subscription_id = <id>``.

Token tiers (Lite/Plus/Pro) carry ``hints_per_cycle`` and a rollover ``cap``;
the Ultimate tier sets ``is_unlimited`` and grants no tokens. Annual plans are
dripped monthly via lazy accrual (``accrual_rate`` / ``paid_until`` /
``last_accrued_at``) so there is no scheduler.
"""

from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from dating.models.base import Base
from dating.utils.datetime import utcnow

# Lifecycle states.
SUB_PENDING = "pending"  # mock checkout created, not yet "paid"
SUB_ACTIVE = "active"
SUB_PAST_DUE = "past_due"
SUB_PAUSED = "paused"
SUB_CANCELED = "canceled"

# Billing intervals.
INTERVAL_MONTH = "month"
INTERVAL_YEAR = "year"


def _new_id() -> str:
    """Generate a compact hex id for a subscription."""
    return uuid4().hex


class Subscription(Base):
    """A user's recurring plan: tier, interval, status, and grant schedule."""

    __tablename__ = "subscriptions"
    __repr_attrs__ = ["id", "tier", "billing_interval", "status"]

    id: Mapped[str] = mapped_column(sa.String(40), primary_key=True, default=_new_id)
    # Paddle's subscription id (mock value while billing is mocked). Unique so a
    # webhook always resolves to exactly one row.
    paddle_subscription_id: Mapped[str] = mapped_column(
        sa.String(255), unique=True, index=True, nullable=False
    )
    paddle_customer_id: Mapped[str | None] = mapped_column(
        sa.String(255), nullable=True, index=True
    )

    tier: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    billing_interval: Mapped[str] = mapped_column(sa.String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=SUB_PENDING, server_default=SUB_PENDING
    )

    # Token tiers: hints granted per monthly cycle + rollover cap. Ultimate: 0.
    hints_per_cycle: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    cap: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    is_unlimited: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )

    # Period + accrual bookkeeping (epoch-less naive UTC; lazy monthly drip).
    current_period_start: Mapped[datetime | None] = mapped_column(sa.DateTime(), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(sa.DateTime(), nullable=True)
    # Paid-through date — the horizon up to which monthly drips may accrue.
    paid_until: Mapped[datetime | None] = mapped_column(sa.DateTime(), nullable=True)
    # Last monthly drip we credited (for annual lazy accrual).
    last_accrued_at: Mapped[datetime | None] = mapped_column(sa.DateTime(), nullable=True)
    # Last cycle period we granted, for idempotency on monthly renewals.
    last_granted_period: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    # Scheduled change to apply at period end (downgrade / interval switch).
    # Upgrades apply immediately, so they never set this. None = no change.
    scheduled_plan_id: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    # When true, the plan ends at period end (cancel takes effect next cycle).
    cancel_at_period_end: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )

    canceled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(), nullable=False, index=True, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )

    @property
    def is_live(self) -> bool:
        """True when the plan still confers benefits (active or in grace)."""
        return self.status in (SUB_ACTIVE, SUB_PAST_DUE, SUB_PAUSED)
