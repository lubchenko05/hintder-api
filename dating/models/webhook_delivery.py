"""The ``webhook_deliveries`` table — audit of inbound publish webhooks.

One row per delivery attempt from an external publisher (SiteOps today).
Deduplication happens HERE and only here: the delivery id is unique per
provider, so a retry of the same delivery becomes a ``duplicate`` answer with
no side effects, while the same slug arriving under a NEW delivery id is a
legitimate content update. Keeping every attempt (accepted, duplicate,
rejected, failed) makes "what did SiteOps actually send us" answerable without
guessing from logs.
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from dating.models.base import Base
from dating.utils.datetime import utcnow

PROVIDER_SITEOPS = "siteops"

DELIVERY_ACCEPTED = "accepted"
DELIVERY_DUPLICATE = "duplicate"
DELIVERY_IGNORED = "ignored"
DELIVERY_REJECTED = "rejected"
DELIVERY_FAILED = "failed"


class WebhookDelivery(Base):
    """One inbound webhook delivery and what became of it."""

    __tablename__ = "webhook_deliveries"
    __repr_attrs__ = ["provider", "delivery_id", "status"]

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    delivery_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(60), nullable=False, default="")
    # Informational — lets us see whether a "duplicate" retry carried the same
    # bytes without storing the whole body twice.
    body_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    post_id: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        sa.UniqueConstraint("provider", "delivery_id", name="uq_webhook_deliveries_provider_id"),
    )
