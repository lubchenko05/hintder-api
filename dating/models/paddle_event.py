"""The ``paddle_events`` table — raw inbound webhook log for idempotency + audit.

Every verified webhook is recorded keyed by Paddle's ``event_id`` (unique). A
re-delivered event is recognised and skipped, so billing side effects run once.
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dating.models.base import Base
from dating.utils.datetime import utcnow


class PaddleEvent(Base):
    """A single Paddle webhook event and whether we've processed it."""

    __tablename__ = "paddle_events"
    __repr_attrs__ = ["event_id", "event_type", "processed"]

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(sa.String(255), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(), nullable=False, index=True, default=utcnow
    )
