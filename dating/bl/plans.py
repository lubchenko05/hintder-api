"""Subscription plan catalogue — the source of truth for tiers and prices.

Four tiers (Lite / Plus / Pro / Ultimate), each billable monthly or yearly, so
eight plans. Ultimate is unlimited (``hints_per_cycle`` is 0, ``is_unlimited``
True); the token tiers grant ``hints_per_cycle`` per MONTH — yearly plans drip
that same monthly amount across the paid year (lazy accrual), they don't dump a
year up front. ``plan_id`` is ``{tier}_{interval}`` and maps 1:1 to a Paddle
price id when billing goes live (the webhook resolves a price id back to a plan
through this table — never by hardcoding amounts).
"""

from typing import NamedTuple

from pydantic import BaseModel

from dating.models.subscription import INTERVAL_MONTH, INTERVAL_YEAR
from dating.utils.error_handler import BadRequestException

TIER_LITE = "lite"
TIER_PLUS = "plus"
TIER_PRO = "pro"
TIER_ULTIMATE = "ultimate"

# Numeric rank used to decide upgrade vs downgrade direction.
TIER_RANK: dict[str, int] = {
    TIER_LITE: 0,
    TIER_PLUS: 1,
    TIER_PRO: 2,
    TIER_ULTIMATE: 3,
}


class Plan(BaseModel):
    """One purchasable subscription plan (a tier at a billing interval)."""

    id: str
    tier: str
    label: str
    billing_interval: str
    price_usd: float
    # Monthly token allotment (0 for unlimited). Yearly plans drip this monthly.
    hints_per_cycle: int
    is_unlimited: bool

    @property
    def amount_cents(self) -> int:
        """Price in integer cents, for storage + Paddle."""
        return round(self.price_usd * 100)


class _TierSpec(NamedTuple):
    """Per-tier config: monthly allotment + monthly/yearly prices."""

    tier: str
    label: str
    hints: int
    month_price: float
    year_price: float
    unlimited: bool


# Keep in sync with the dating-next pricing page + Paddle. Yearly ≈ 2 months free.
_TIERS: list[_TierSpec] = [
    _TierSpec(TIER_LITE, "Lite", 10, 4.99, 49.0, False),
    _TierSpec(TIER_PLUS, "Plus", 25, 9.99, 99.0, False),
    _TierSpec(TIER_PRO, "Pro", 100, 19.99, 199.0, False),
    _TierSpec(TIER_ULTIMATE, "Ultimate", 0, 49.99, 499.0, True),
]


def _build_plans() -> dict[str, Plan]:
    """Expand the tier table into the eight {tier}_{interval} plans."""
    plans: dict[str, Plan] = {}
    for t in _TIERS:
        for interval, price in (
            (INTERVAL_MONTH, t.month_price),
            (INTERVAL_YEAR, t.year_price),
        ):
            plan = Plan(
                id=f"{t.tier}_{interval}",
                tier=t.tier,
                label=t.label,
                billing_interval=interval,
                price_usd=price,
                hints_per_cycle=t.hints,
                is_unlimited=t.unlimited,
            )
            plans[plan.id] = plan
    return plans


PLANS_BY_ID: dict[str, Plan] = _build_plans()
PLANS: list[Plan] = list(PLANS_BY_ID.values())


def get_plan_or_error(plan_id: str) -> Plan:
    """Return the plan for ``plan_id`` or raise ``BadRequestException``."""
    plan = PLANS_BY_ID.get(plan_id)
    if plan is None:
        raise BadRequestException(f"Unknown plan '{plan_id}'")
    return plan
