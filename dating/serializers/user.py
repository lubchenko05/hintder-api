"""User-facing response serializers (``/me``)."""

from datetime import datetime

from dating.serializers.base import BaseSerializer


class UserSerializer(BaseSerializer):
    """The authenticated user's profile + current hint balance."""

    id: str
    email: str | None
    name: str | None
    avatar: str | None
    free_hints: int
    paid_hints: int
    total_hints: int
    created_at: datetime
