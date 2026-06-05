"""The ``matches`` table — a user's persisted match (analysis + thread).

Stores the full match the frontend works with: the profile analysis blob, the
conversation so far, the picked voice/risk, and status. Timestamps are epoch
milliseconds to round-trip the frontend's ``Date.now()`` values verbatim.
Conversation screenshots are stripped before persistence (privacy + size).
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dating.models.base import Base
from dating.utils.datetime import utcnow

MATCH_IN_PROGRESS = "in_progress"
MATCH_ASKED_OUT = "asked_out"


def _new_id() -> str:
    """Generate a compact hex id for a match."""
    return uuid4().hex


class Match(Base):
    """One match: profile analysis, conversation, picked settings, status."""

    __tablename__ = "matches"
    __repr_attrs__ = ["id", "user_id", "name", "status"]

    id: Mapped[str] = mapped_column(sa.String(40), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        sa.String(255), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    age: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=MATCH_IN_PROGRESS, server_default=MATCH_IN_PROGRESS
    )
    picked_style: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    picked_tone: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    conversation: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # Generated openers the user paid a hint for — kept so a match resumes with
    # them intact (the client can't regenerate them for free).
    messages: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    # The latest read of her reply (interest level + suggestions). Kept so a
    # resumed match shows the suggestions the user already paid to generate —
    # no second hint spent. Null when it's her turn / nothing read yet.
    follow_up: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Frontend epoch-ms timestamps, stored verbatim for clean round-trips.
    created_at_ms: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    updated_at_ms: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, index=True)
    # Server-side audit timestamp (independent of the client clock).
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
