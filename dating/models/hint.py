"""The ``hint_consumptions`` table — append-only audit log of spent hints.

Balance lives on ``users`` (the fast read path); this table is the ledger that
explains *why* the balance is what it is (one row per hint spent). Useful for
analytics, support, and reconstructing a balance if a counter ever drifts.
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from dating.models.base import Base
from dating.utils.datetime import utcnow


class HintKind(str):
    """String enum of what a hint was spent on (kept as plain str for simplicity)."""


# Allowed ``kind`` values. Plain constants instead of an Enum column so adding a
# kind never needs a migration.
HINT_KIND_PROFILE_READ = "profile_read"
HINT_KIND_REPLY_DRAFT = "reply_draft"

# Allowed ``source`` values (which bucket the hint came from).
HINT_SOURCE_FREE = "free"
HINT_SOURCE_PAID = "paid"  # one-time top-up (uncapped, spent last)
HINT_SOURCE_SUBSCRIPTION = "subscription"  # recurring grant (capped)
HINT_SOURCE_UNLIMITED = "unlimited"  # Ultimate tier — no balance drawn

# Allowed ``HintGrant.source`` values (why hints were ADDED to a balance).
GRANT_SOURCE_FREE = "free"
GRANT_SOURCE_SUBSCRIPTION = "subscription_cycle"
GRANT_SOURCE_ONE_TIME = "one_time"
GRANT_SOURCE_TRANSFER = "account_transfer"
GRANT_SOURCE_CLAWBACK = "refund_clawback"


class HintConsumption(Base):
    """One spent hint: who spent it, on what, from which bucket, and when."""

    __tablename__ = "hint_consumptions"
    __repr_attrs__ = ["id", "user_id", "kind", "source"]

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        sa.String(255), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    source: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    # Optional pointer to the artefact produced (e.g. a profile-read id).
    reference_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(), nullable=False, index=True, default=utcnow
    )


class HintGrant(Base):
    """One ADDED batch of hints: the audit mirror of ``HintConsumption``.

    Every credit to a balance (free grant, subscription cycle, one-time top-up,
    support transfer, refund clawback) lands here. The balance counters on
    ``users`` are a cache; this ledger is the source of truth and what makes
    support transfers + reconciliation auditable. ``period_key`` is the
    per-cycle idempotency tag for subscription grants.
    """

    __tablename__ = "hint_grants"
    __repr_attrs__ = ["id", "user_id", "source", "amount"]

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        sa.String(255), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(sa.String(40), nullable=True, index=True)
    period_key: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(), nullable=False, index=True, default=utcnow
    )
