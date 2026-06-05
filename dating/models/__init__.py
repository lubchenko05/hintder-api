"""SQLAlchemy ORM models. Import every model here so Alembic sees the metadata."""

from dating.models.base import Base, metadata
from dating.models.hint import HintConsumption, HintGrant
from dating.models.match import Match
from dating.models.paddle_event import PaddleEvent
from dating.models.purchase import Purchase
from dating.models.subscription import Subscription
from dating.models.user import User

__all__ = [
    "Base",
    "metadata",
    "User",
    "HintConsumption",
    "HintGrant",
    "Match",
    "Purchase",
    "PaddleEvent",
    "Subscription",
]
