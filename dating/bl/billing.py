"""Billing business logic — subscriptions (recurring) + one-time top-ups.

Subscriptions are the main product (predictable MRR); top-ups are an
intentionally pricier overflow that drops into the same balance. Both checkouts
are mocked while ``paddle_enabled`` is False: the browser is sent to the
frontend's local checkout page and a dev-only "simulate webhook" path grants the
benefit. Granting is idempotent — the atomic state transition is the guard.
"""

import logging

from pydantic import BaseModel

from dating.bl import hints as bl_hints
from dating.bl.plans import get_plan_or_error, Plan
from dating.config import get_config
from dating.models.subscription import (
    INTERVAL_YEAR,
    SUB_ACTIVE,
    SUB_PENDING,
    Subscription,
)
from dating.models.user import User
from dating.services.paddle import CheckoutSession, PaddleService
from dating.storages import DBStorage
from dating.utils.datetime import utcnow
from dating.utils.error_handler import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)

logger = logging.getLogger(__name__)


class HintPack(BaseModel):
    """A one-time top-up pack (overflow, priced above the subscription rate)."""

    id: str
    label: str
    hints: int
    price_usd: float
    original_price_usd: float | None = None

    @property
    def amount_cents(self) -> int:
        """Price in integer cents, for storage and Paddle."""
        return round(self.price_usd * 100)


# Top-up catalogue — deliberately ~$0.50-0.70/hint (pricier than subscriptions)
# so it reads as "no-commitment overflow", not the main way to buy.
HINT_PACKS: list[HintPack] = [
    HintPack(id="topup_10", label="quick top-up", hints=10, price_usd=6.99),
    HintPack(id="topup_30", label="big top-up", hints=30, price_usd=17.99),
    HintPack(id="topup_100", label="bulk top-up", hints=100, price_usd=49.99),
]
PACKS_BY_ID: dict[str, HintPack] = {p.id: p for p in HINT_PACKS}


def get_pack_or_error(pack_id: str) -> HintPack:
    """Return the pack with this id, or raise ``BadRequestException``."""
    pack = PACKS_BY_ID.get(pack_id)
    if pack is None:
        raise BadRequestException(f"Unknown hint pack '{pack_id}'")
    return pack


# ── One-time top-ups ────────────────────────────────────────────────────────


async def create_checkout(
    db: DBStorage,
    paddle: PaddleService,
    *,
    user: User,
    pack_id: str,
) -> CheckoutSession:
    """Create a checkout for a top-up ``pack_id`` and record a pending purchase."""
    pack = get_pack_or_error(pack_id)
    session = await paddle.create_checkout(
        hints=pack.hints,
        price_usd=pack.price_usd,
        customer_email=user.email,
    )
    await db.purchase.create_pending(
        user_id=user.id,
        paddle_transaction_id=session.transaction_id,
        pack_id=pack.id,
        hints=pack.hints,
        amount_cents=pack.amount_cents,
    )
    return session


async def grant_purchase(db: DBStorage, transaction_id: str) -> None:
    """Credit a top-up's hints exactly once (atomic pending→completed guard)."""
    completed = await db.purchase.transition_to_completed(transaction_id)
    if completed is None:
        logger.info("Purchase %s already completed or missing; skipping grant", transaction_id)
        return
    await db.hint.add_topup_hints(completed.user_id, completed.hints)


# ── Subscriptions ───────────────────────────────────────────────────────────


def _cap_for(plan: Plan) -> int:
    """Rollover cap = N monthly cycles of the plan's allotment (0 if unlimited)."""
    if plan.is_unlimited:
        return 0
    return plan.hints_per_cycle * get_config().rollover_cap_cycles


async def create_subscription_checkout(
    db: DBStorage,
    paddle: PaddleService,
    *,
    user: User,
    plan_id: str,
) -> CheckoutSession:
    """Start a subscription checkout and stage a pending ``Subscription`` row."""
    plan = get_plan_or_error(plan_id)
    session = await paddle.create_subscription_checkout(
        plan_id=plan.id,
        price_usd=plan.price_usd,
        hints_per_cycle=plan.hints_per_cycle,
        customer_email=user.email,
    )
    await db.subscription.create_for_user(
        user_id=user.id,
        paddle_subscription_id=session.transaction_id,
        tier=plan.tier,
        billing_interval=plan.billing_interval,
        hints_per_cycle=plan.hints_per_cycle,
        cap=_cap_for(plan),
        is_unlimited=plan.is_unlimited,
        status=SUB_PENDING,
        paddle_customer_id=user.paddle_customer_id,
    )
    return session


async def _activate_subscription(db: DBStorage, sub: Subscription, user_id: str) -> None:
    """Flip a pending subscription to active, set its periods, grant cycle one.

    Idempotent: an already-active subscription is left untouched (its first cycle
    was granted on the first activation).
    """
    if sub.status == SUB_ACTIVE:
        return

    now = utcnow()
    months = 12 if sub.billing_interval == INTERVAL_YEAR else 1
    period_end = bl_hints.add_months(now, months)
    period_key = f"cycle:{now.date().isoformat()}"

    await db.subscription.update_fields(
        sub.id,
        status=SUB_ACTIVE,
        current_period_start=now,
        current_period_end=period_end,
        paid_until=period_end,
        last_accrued_at=now,
        last_granted_period=period_key,
    )
    # Token tiers get their first month immediately; the rest of a yearly plan
    # drips monthly via lazy accrual. Ultimate grants no balance. We SET (not
    # add) so (re)subscribing or switching plans replaces the bucket — it never
    # stacks. Rollover only happens on renewals/drip (which add, capped).
    if not sub.is_unlimited:
        await db.hint.set_subscription_hints(
            user_id,
            amount=sub.hints_per_cycle,
            subscription_id=sub.id,
            period_key=period_key,
        )


async def complete_mock(
    db: DBStorage,
    paddle: PaddleService,
    *,
    user: User,
    transaction_id: str,
) -> User:
    """Dev-only: simulate the Paddle webhook for a mock checkout.

    Dispatches to either a top-up purchase or a subscription by the transaction
    id. Refuses to run once real Paddle is enabled (the webhook is the only grant
    path then). Returns the refreshed user.
    """
    if paddle.enabled:
        raise ForbiddenException("Mock completion is disabled when Paddle is live")

    purchase = await db.purchase.get_by_transaction_id(transaction_id)
    if purchase is not None:
        if purchase.user_id != user.id:
            raise NotFoundException("Purchase not found")
        await grant_purchase(db, transaction_id)
        return await db.user.get_by_id_or_error(user.id)

    sub = await db.subscription.get_by_paddle_id(transaction_id)
    if sub is not None:
        owner_id = await db.subscription.owner_id(sub.id)
        if owner_id != user.id:
            raise NotFoundException("Subscription not found")
        await _activate_subscription(db, sub, user.id)
        return await db.user.get_by_id_or_error(user.id)

    raise NotFoundException("Checkout not found")


async def current_subscription(db: DBStorage, user: User) -> Subscription | None:
    """Return the user's live subscription (active/past_due/paused), else ``None``."""
    if user.subscription_id is None:
        return None
    sub = await db.subscription.get_by_id(user.subscription_id)
    if sub is None or not sub.is_live:
        return None
    return sub


async def upgrade_subscription(db: DBStorage, *, user: User, new_plan_id: str) -> User:
    """Upgrade to a higher tier immediately, topping the balance up to the new plan.

    Sets ``sub_hints`` to ``max(current, new_allotment)`` — so upgrading gives the
    new tier's allotment if you have less, but never stacks on top if you already
    have more. This is intentionally a SET (not an add): adding the per-cycle
    difference would let an upgrade → downgrade → upgrade loop farm free hints,
    because a downgrade keeps the balance while lowering the plan's allotment.
    """
    sub = await current_subscription(db, user)
    if sub is None:
        raise BadRequestException("No active subscription to upgrade")
    new_plan = get_plan_or_error(new_plan_id)
    new_cap = _cap_for(new_plan)
    await db.subscription.update_fields(
        sub.id,
        tier=new_plan.tier,
        billing_interval=new_plan.billing_interval,
        hints_per_cycle=new_plan.hints_per_cycle,
        cap=new_cap,
        is_unlimited=new_plan.is_unlimited,
        # Clear any pending downgrade / cancellation.
        scheduled_plan_id=None,
        cancel_at_period_end=False,
    )
    if not new_plan.is_unlimited:
        target = max(user.sub_hints, new_plan.hints_per_cycle)
        await db.hint.set_subscription_hints(
            user.id,
            amount=target,
            subscription_id=sub.id,
            period_key=f"upgrade:{utcnow().date().isoformat()}",
        )
    return await db.user.get_by_id_or_error(user.id)


async def downgrade_subscription(db: DBStorage, *, user: User, new_plan_id: str) -> Subscription:
    """Switch to a lower (or same-rank) plan immediately, keeping hints.

    The new tier applies right away so the UI reflects it, but we do NOT subtract
    hints — the user keeps their current balance. The lower allotment + cap take
    effect for future cycles. Returns the updated subscription.
    """
    sub = await current_subscription(db, user)
    if sub is None:
        raise BadRequestException("No active subscription to change")
    new_plan = get_plan_or_error(new_plan_id)
    return await db.subscription.update_fields(
        sub.id,
        tier=new_plan.tier,
        billing_interval=new_plan.billing_interval,
        hints_per_cycle=new_plan.hints_per_cycle,
        cap=_cap_for(new_plan),
        is_unlimited=new_plan.is_unlimited,
        scheduled_plan_id=None,
        cancel_at_period_end=False,
    )


async def cancel_subscription(db: DBStorage, user: User) -> Subscription:
    """Schedule cancellation at the end of the current billing period.

    The plan stays active until ``current_period_end`` — hints are not touched.
    Sets ``cancel_at_period_end=True`` (cleared if the user re-subscribes).
    Returns the updated subscription so the UI can show the end date.
    """
    sub = await current_subscription(db, user)
    if sub is None:
        raise BadRequestException("No active subscription to cancel")
    return await db.subscription.update_fields(sub.id, cancel_at_period_end=True)


async def reattach_subscription(db: DBStorage, *, sub_id: str, to_user_id: str) -> None:
    """Support-only: move a subscription (and the old owner's balance) to a user.

    Used when someone loses access to an account whose subscription is still
    live. Transfers the donor's accumulated hints to the recipient, then
    re-points the subscription FK. No-op-safe if the donor is the recipient.
    """
    sub = await db.subscription.get_by_id(sub_id)
    if sub is None:
        raise NotFoundException(f"Subscription {sub_id} not found")
    recipient = await db.user.get_by_id(to_user_id)
    if recipient is None:
        raise NotFoundException(f"User {to_user_id} not found")

    from_user_id = await db.subscription.owner_id(sub_id)
    if from_user_id is not None and from_user_id != to_user_id:
        await db.hint.transfer_balance(from_user_id=from_user_id, to_user_id=to_user_id)
    await db.subscription.relink(sub_id=sub_id, from_user_id=from_user_id, to_user_id=to_user_id)
