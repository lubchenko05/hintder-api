"""Hint balance + consumption-history serializers."""

from datetime import datetime

from dating.serializers.base import BaseSerializer, BaseValidator


class HintBalanceSerializer(BaseSerializer):
    """The user's current spendable hint balance (free + subscription + top-up)."""

    free_hints: int
    sub_hints: int
    paid_hints: int
    total_hints: int


class ConsumeHintValidator(BaseValidator):
    """``POST /hints/consume`` body — what the hint is being spent on."""

    kind: str = "profile_read"


class HintConsumptionSerializer(BaseSerializer):
    """One ledger row — a single spent hint."""

    id: int
    kind: str
    source: str
    reference_id: str | None
    created_at: datetime
