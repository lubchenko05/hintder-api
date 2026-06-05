"""Billing request validators + response serializers."""

from datetime import datetime

from dating.serializers.base import BaseSerializer, BaseValidator
from dating.serializers.hints import HintBalanceSerializer
from dating.validators import NonEmptyStr


class ClaimAssetsValidator(BaseValidator):
    """``POST /me/claim`` body — the previous (anonymous) account's backend JWT."""

    prev_token: NonEmptyStr


class HintPackSerializer(BaseSerializer):
    """A purchasable hint pack for the pricing UI."""

    id: str
    label: str
    hints: int
    price_usd: float
    original_price_usd: float | None


class CheckoutValidator(BaseValidator):
    """``POST /billing/checkout`` body — which pack to buy."""

    pack_id: NonEmptyStr


class CheckoutSessionSerializer(BaseSerializer):
    """``POST /billing/checkout`` response — where to send the browser."""

    transaction_id: str
    checkout_url: str
    hints: int
    price_usd: float
    is_mock: bool


class MockCompleteValidator(BaseValidator):
    """``POST /billing/mock/complete`` body — the txn from the mock checkout."""

    transaction_id: NonEmptyStr


class MockCompleteSerializer(BaseSerializer):
    """``POST /billing/mock/complete`` response — the post-grant balance."""

    balance: HintBalanceSerializer


class PlanSerializer(BaseSerializer):
    """A subscription plan for the pricing UI."""

    id: str
    tier: str
    label: str
    billing_interval: str
    price_usd: float
    hints_per_cycle: int
    is_unlimited: bool


class SubscribeValidator(BaseValidator):
    """``POST /billing/subscribe`` body — which plan to subscribe to."""

    plan_id: NonEmptyStr


class ChangePlanValidator(BaseValidator):
    """``POST /billing/change-plan`` body — the target plan id."""

    plan_id: NonEmptyStr


class SubscriptionSerializer(BaseSerializer):
    """The user's live subscription state for the account UI."""

    id: str
    tier: str
    billing_interval: str
    status: str
    is_unlimited: bool
    hints_per_cycle: int
    cap: int
    current_period_end: datetime | None
    paid_until: datetime | None
    cancel_at_period_end: bool
    scheduled_plan_id: str | None
