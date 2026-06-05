"""Billing endpoints — plans + top-up packs, checkout, dev mock-completion."""

from fastapi import APIRouter, Depends, Response, status

from dating.bl import billing as bl_billing, plans as bl_plans
from dating.bl.plans import get_plan_or_error, TIER_RANK
from dating.dependencies import get_current_user, get_db_storage, get_paddle_service
from dating.models.user import User
from dating.serializers.billing import (
    ChangePlanValidator,
    CheckoutSessionSerializer,
    CheckoutValidator,
    ClaimAssetsValidator,
    HintPackSerializer,
    MockCompleteSerializer,
    MockCompleteValidator,
    PlanSerializer,
    SubscribeValidator,
    SubscriptionSerializer,
)
from dating.serializers.hints import HintBalanceSerializer
from dating.services.paddle import PaddleService
from dating.storages import DBStorage
from dating.utils.error_handler import BadRequestException
from dating.utils.jwt import decode_access_token

router = APIRouter()


@router.get("/billing/plans", response_model=list[PlanSerializer], tags=["billing"])
async def list_plans() -> list[PlanSerializer]:
    """Return the subscription plan catalogue (public — no auth required)."""
    return [PlanSerializer.model_validate(p) for p in bl_plans.PLANS]


@router.get("/billing/packs", response_model=list[HintPackSerializer], tags=["billing"])
async def list_packs() -> list[HintPackSerializer]:
    """Return the one-time top-up catalogue (public — no auth required)."""
    return [HintPackSerializer.model_validate(p) for p in bl_billing.HINT_PACKS]


@router.post("/billing/checkout", response_model=CheckoutSessionSerializer, tags=["billing"])
async def create_checkout(
    payload: CheckoutValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
    paddle: PaddleService = Depends(get_paddle_service),
) -> CheckoutSessionSerializer:
    """Start checkout for a one-time top-up pack."""
    session = await bl_billing.create_checkout(db, paddle, user=user, pack_id=payload.pack_id)
    return CheckoutSessionSerializer.model_validate(session)


@router.post("/billing/subscribe", response_model=CheckoutSessionSerializer, tags=["billing"])
async def subscribe(
    payload: SubscribeValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
    paddle: PaddleService = Depends(get_paddle_service),
) -> CheckoutSessionSerializer:
    """Start a subscription checkout for a plan and return where to send the browser."""
    session = await bl_billing.create_subscription_checkout(
        db, paddle, user=user, plan_id=payload.plan_id
    )
    return CheckoutSessionSerializer.model_validate(session)


@router.post("/billing/mock/complete", response_model=MockCompleteSerializer, tags=["billing"])
async def complete_mock(
    payload: MockCompleteValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
    paddle: PaddleService = Depends(get_paddle_service),
) -> MockCompleteSerializer:
    """Dev-only: simulate the Paddle webhook to grant a mock top-up OR subscription."""
    refreshed = await bl_billing.complete_mock(
        db, paddle, user=user, transaction_id=payload.transaction_id
    )
    return MockCompleteSerializer(balance=HintBalanceSerializer.model_validate(refreshed))


@router.get("/me/subscription", response_model=SubscriptionSerializer | None, tags=["billing"])
async def get_subscription(
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
) -> SubscriptionSerializer | None:
    """Return the user's live subscription, or ``null`` if they have none."""
    sub = await bl_billing.current_subscription(db, user)
    return SubscriptionSerializer.model_validate(sub) if sub is not None else None


@router.post("/me/claim", status_code=status.HTTP_204_NO_CONTENT, tags=["billing"])
async def claim_assets(
    payload: ClaimAssetsValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
) -> Response:
    """Bring a just-abandoned anonymous account's subscription + hints to this user.

    For the 'pay anonymously, sign in after' flow: the previous anonymous backend
    JWT proves ownership of that account; we move its subscription + balance here
    (no-op if the uid didn't change). An invalid prev token is silently ignored.
    """
    try:
        prev_uid = decode_access_token(payload.prev_token).get("sub")
    except Exception:
        prev_uid = None
    if isinstance(prev_uid, str) and prev_uid:
        await bl_billing.claim_anonymous_assets(db, prev_user_id=prev_uid, to_user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/billing/change-plan", response_model=SubscriptionSerializer, tags=["billing"])
async def change_plan(
    payload: ChangePlanValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
) -> SubscriptionSerializer:
    """Upgrade (immediate + delta hints) or downgrade/switch (scheduled for next cycle).

    The view decides which path to take based on tier rank: moving to a higher-ranked
    plan is an upgrade, moving to a lower-ranked or same tier on a different interval
    is a scheduled change.
    """
    sub = await bl_billing.current_subscription(db, user)
    if sub is None:
        raise BadRequestException("No active subscription")

    new_plan = get_plan_or_error(payload.plan_id)
    cur_rank = TIER_RANK.get(sub.tier, 0)
    new_rank = TIER_RANK.get(new_plan.tier, 0)
    is_upgrade = new_rank > cur_rank

    if is_upgrade:
        await bl_billing.upgrade_subscription(db, user=user, new_plan_id=payload.plan_id)
    else:
        await bl_billing.downgrade_subscription(db, user=user, new_plan_id=payload.plan_id)

    refreshed_sub = await bl_billing.current_subscription(db, user)
    assert refreshed_sub is not None
    return SubscriptionSerializer.model_validate(refreshed_sub)


@router.post("/billing/cancel", response_model=SubscriptionSerializer, tags=["billing"])
async def cancel_subscription(
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
) -> SubscriptionSerializer:
    """Schedule cancellation at period end (keeps hints, plan active until then)."""
    sub = await bl_billing.cancel_subscription(db, user)
    return SubscriptionSerializer.model_validate(sub)
