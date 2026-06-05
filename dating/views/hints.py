"""Hint balance + history endpoints."""

from fastapi import APIRouter, Depends

from dating.bl import hints as bl_hints
from dating.dependencies import (
    get_current_user,
    get_db_storage,
    PaginatedResponse,
    Paginator,
)
from dating.models.user import User
from dating.serializers.hints import (
    ConsumeHintValidator,
    HintBalanceSerializer,
    HintConsumptionSerializer,
)
from dating.storages import DBStorage

router = APIRouter()


@router.get("/me/hints", response_model=HintBalanceSerializer, tags=["hints"])
async def get_balance(user: User = Depends(get_current_user)) -> HintBalanceSerializer:
    """Return the authenticated user's current hint balance."""
    return HintBalanceSerializer.model_validate(user)


@router.post("/hints/consume", response_model=HintBalanceSerializer, tags=["hints"])
async def consume_hint(
    payload: ConsumeHintValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
) -> HintBalanceSerializer:
    """Spend one hint (free bucket first); 402 when the balance is empty."""
    refreshed, _ = await bl_hints.consume_hint(db, user.id, kind=payload.kind)
    return HintBalanceSerializer.model_validate(refreshed)


@router.get(
    "/me/hints/history",
    response_model=PaginatedResponse[HintConsumptionSerializer],
    tags=["hints"],
)
async def get_history(
    user: User = Depends(get_current_user),
    paginator: Paginator = Depends(),
    db: DBStorage = Depends(get_db_storage),
) -> PaginatedResponse[HintConsumptionSerializer]:
    """Return a page of the user's hint-consumption ledger, newest first."""
    rows, total = await db.hint.list_consumptions(
        user.id, limit=paginator.limit, offset=paginator.offset
    )
    return PaginatedResponse[HintConsumptionSerializer](
        items=[HintConsumptionSerializer.model_validate(r) for r in rows],
        total=total,
        limit=paginator.limit,
        offset=paginator.offset,
    )
