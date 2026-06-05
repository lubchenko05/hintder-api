"""Hint business logic — spend a hint, with the rules in one place.

Two spend modes, resolved by ``precheck``:
- *balance*: draw one hint (free → subscription → paid), the classic path.
- *unlimited*: an Ultimate subscriber draws no balance; the read is logged and
  counted against a daily fair-use limit.

Also owns lazy monthly accrual for ANNUAL plans: a yearly subscription is paid
up front but its hints drip in monthly, credited on-access here (no scheduler).
``precheck`` runs before the (paid) Gemini call to fail fast; ``commit`` records
the spend only after it succeeds. ``consume_hint`` is the legacy single-shot
spend kept for the standalone ``/hints/consume`` endpoint.
"""

from datetime import datetime

from dating.config import get_config
from dating.models.hint import HintConsumption
from dating.models.subscription import INTERVAL_YEAR
from dating.models.user import User
from dating.storages import DBStorage
from dating.utils.datetime import utcnow
from dating.utils.error_handler import (
    PaymentRequiredException,
    TooManyRequestsException,
)

MODE_BALANCE = "balance"
MODE_UNLIMITED = "unlimited"

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


async def consume_hint(
    db: DBStorage,
    user_id: str,
    *,
    kind: str,
    reference_id: str | None = None,
) -> tuple[User, HintConsumption]:
    """Spend one hint for ``user_id`` on ``kind``; raise 402 if the balance is empty."""
    return await db.hint.consume(user_id, kind=kind, reference_id=reference_id)


def _is_leap(year: int) -> bool:
    """True if ``year`` is a Gregorian leap year."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _add_one_month(dt: datetime) -> datetime:
    """Return ``dt`` advanced by one calendar month (clamping the day)."""
    month = dt.month % 12 + 1
    year = dt.year + (1 if dt.month == 12 else 0)
    days = _DAYS_IN_MONTH[month - 1] + (1 if month == 2 and _is_leap(year) else 0)
    return dt.replace(year=year, month=month, day=min(dt.day, days))


def add_months(dt: datetime, n: int) -> datetime:
    """Return ``dt`` advanced by ``n`` calendar months (day-clamped)."""
    out = dt
    for _ in range(n):
        out = _add_one_month(out)
    return out


async def accrue_due(db: DBStorage, user: User) -> User:
    """Drip any monthly cycles a yearly plan has earned but not yet credited.

    No-op for users without a live yearly token subscription. Idempotent: the
    advanced ``last_accrued_at`` is the guard, so re-running grants nothing new.
    """
    sub_id = user.subscription_id
    if sub_id is None:
        return user
    sub = await db.subscription.get_by_id(sub_id)
    if (
        sub is None
        or not sub.is_live
        or sub.is_unlimited
        or sub.billing_interval != INTERVAL_YEAR
        or sub.paid_until is None
        or sub.last_accrued_at is None
    ):
        return user

    horizon = min(utcnow(), sub.paid_until)
    cursor = sub.last_accrued_at
    cycles = 0
    while _add_one_month(cursor) <= horizon:
        cursor = _add_one_month(cursor)
        cycles += 1
    if cycles == 0:
        return user

    refreshed = await db.hint.grant_subscription_hints(
        user.id,
        amount=cycles * sub.hints_per_cycle,
        cap=sub.cap,
        subscription_id=sub.id,
        period_key=f"accrue:{cursor.date().isoformat()}",
    )
    await db.subscription.update_fields(sub.id, last_accrued_at=cursor)
    return refreshed


async def precheck(db: DBStorage, user: User) -> str:
    """Resolve how this read will be paid, failing fast if it can't be.

    Accrues any due monthly drip first, then returns ``MODE_UNLIMITED`` for a
    live Ultimate plan (raising 429 if the daily fair-use limit is already hit)
    or ``MODE_BALANCE`` otherwise (raising 402 if the balance is empty).
    """
    cfg = get_config()
    user = await accrue_due(db, user)

    if user.subscription_id is not None:
        sub = await db.subscription.get_by_id(user.subscription_id)
        if sub is not None and sub.is_live and sub.is_unlimited:
            today = utcnow().date()
            used = user.ultimate_used if user.ultimate_day == today else 0
            if used >= cfg.fair_use_daily_limit:
                raise TooManyRequestsException("Daily fair-use limit reached — try again tomorrow")
            return MODE_UNLIMITED

    if user.total_hints <= 0:
        raise PaymentRequiredException("Out of hints")
    return MODE_BALANCE


async def commit(
    db: DBStorage, user: User, *, kind: str, mode: str, reference_id: str | None = None
) -> None:
    """Record the spend after a successful read, per the resolved ``mode``."""
    cfg = get_config()
    if mode == MODE_UNLIMITED:
        await db.hint.consume_unlimited(
            user.id, kind=kind, daily_limit=cfg.fair_use_daily_limit, reference_id=reference_id
        )
    else:
        await db.hint.consume(user.id, kind=kind, reference_id=reference_id)
