"""Data access for hint balance mutations + the consumption/grant ledgers.

This storage owns the atomic balance mutations on ``users`` and both ledgers
(``hint_consumptions`` for spends, ``hint_grants`` for credits). Keeping the
counter change and the ledger insert in one transaction is what makes spending
and granting safe under concurrency.

Spend order is free → subscription → paid (top-up kept for last). Subscription
grants are capped (the cap protects retention + bounds liability); top-ups are
never capped. Ultimate users draw no balance — their reads are logged and
counted against a daily fair-use limit instead.
"""

import sqlalchemy as sa

from dating.models.hint import (
    GRANT_SOURCE_ONE_TIME,
    GRANT_SOURCE_SUBSCRIPTION,
    GRANT_SOURCE_TRANSFER,
    HINT_SOURCE_FREE,
    HINT_SOURCE_PAID,
    HINT_SOURCE_SUBSCRIPTION,
    HINT_SOURCE_UNLIMITED,
    HintConsumption,
    HintGrant,
)
from dating.models.user import User
from dating.storages.base import BaseStorage
from dating.utils.datetime import utcnow
from dating.utils.error_handler import (
    NotFoundException,
    PaymentRequiredException,
    TooManyRequestsException,
)


class HintStorage(BaseStorage):
    """Atomic hint spend / top-up / grant plus ledger reads."""

    async def consume(
        self,
        user_id: str,
        *,
        kind: str,
        reference_id: str | None = None,
    ) -> tuple[User, HintConsumption]:
        """Spend one hint atomically, draining free → subscription → paid.

        Locks the user row ``FOR UPDATE`` so concurrent spends can't double-draw.
        Raises ``NotFoundException`` if the user is missing and
        ``PaymentRequiredException`` if every bucket is empty.
        """
        async with self._begin() as session:
            user = await session.get(User, user_id, with_for_update=True)
            if user is None:
                raise NotFoundException(f"User {user_id} not found")

            if user.free_hints > 0:
                user.free_hints -= 1
                source = HINT_SOURCE_FREE
            elif user.sub_hints > 0:
                user.sub_hints -= 1
                source = HINT_SOURCE_SUBSCRIPTION
            elif user.paid_hints > 0:
                user.paid_hints -= 1
                source = HINT_SOURCE_PAID
            else:
                raise PaymentRequiredException("Out of hints")

            user.updated_at = utcnow()
            consumption = HintConsumption(
                user_id=user_id, kind=kind, source=source, reference_id=reference_id
            )
            session.add(consumption)
            await session.flush()
            await session.refresh(user)
            await session.refresh(consumption)
            return user, consumption

    async def consume_unlimited(
        self,
        user_id: str,
        *,
        kind: str,
        daily_limit: int,
        reference_id: str | None = None,
    ) -> tuple[User, HintConsumption]:
        """Log an Ultimate read without drawing balance, enforcing a daily cap.

        Resets the per-day counter when the UTC date rolls over. Raises
        ``TooManyRequestsException`` once the daily fair-use limit is hit.
        """
        today = utcnow().date()
        async with self._begin() as session:
            user = await session.get(User, user_id, with_for_update=True)
            if user is None:
                raise NotFoundException(f"User {user_id} not found")

            used = user.ultimate_used if user.ultimate_day == today else 0
            if used >= daily_limit:
                raise TooManyRequestsException("Daily fair-use limit reached — try again tomorrow")

            user.ultimate_day = today
            user.ultimate_used = used + 1
            user.updated_at = utcnow()
            consumption = HintConsumption(
                user_id=user_id, kind=kind, source=HINT_SOURCE_UNLIMITED, reference_id=reference_id
            )
            session.add(consumption)
            await session.flush()
            await session.refresh(user)
            await session.refresh(consumption)
            return user, consumption

    async def grant_subscription_hints(
        self,
        user_id: str,
        *,
        amount: int,
        cap: int,
        subscription_id: str,
        period_key: str,
    ) -> User:
        """Credit a subscription cycle's hints, clamped to the rollover ``cap``.

        Only the amount that actually lands (after the cap) is recorded in the
        grant ledger. Returns the refreshed user.
        """
        async with self._begin() as session:
            user = await session.get(User, user_id, with_for_update=True)
            if user is None:
                raise NotFoundException(f"User {user_id} not found")

            target = user.sub_hints + amount
            if cap > 0:
                target = min(target, cap)
            granted = max(target - user.sub_hints, 0)
            user.sub_hints = target
            user.updated_at = utcnow()
            session.add(
                HintGrant(
                    user_id=user_id,
                    amount=granted,
                    source=GRANT_SOURCE_SUBSCRIPTION,
                    subscription_id=subscription_id,
                    period_key=period_key,
                )
            )
            await session.flush()
            await session.refresh(user)
            return user

    async def set_subscription_hints(
        self,
        user_id: str,
        *,
        amount: int,
        subscription_id: str,
        period_key: str,
    ) -> User:
        """Set the subscription bucket to ``amount`` (replace, not add).

        Used when a plan is (re)activated or switched — the new plan's cycle
        replaces whatever subscription hints were there, so re-subscribing never
        stacks. Recorded in the grant ledger. Returns the refreshed user.
        """
        async with self._begin() as session:
            user = await session.get(User, user_id, with_for_update=True)
            if user is None:
                raise NotFoundException(f"User {user_id} not found")
            user.sub_hints = amount
            user.updated_at = utcnow()
            session.add(
                HintGrant(
                    user_id=user_id,
                    amount=amount,
                    source=GRANT_SOURCE_SUBSCRIPTION,
                    subscription_id=subscription_id,
                    period_key=period_key,
                )
            )
            await session.flush()
            await session.refresh(user)
            return user

    async def add_topup_hints(self, user_id: str, amount: int) -> User:
        """Credit a one-time top-up to the (uncapped) paid bucket + ledger."""
        async with self._begin() as session:
            user = await session.get(User, user_id, with_for_update=True)
            if user is None:
                raise NotFoundException(f"User {user_id} not found")
            user.paid_hints += amount
            user.updated_at = utcnow()
            session.add(HintGrant(user_id=user_id, amount=amount, source=GRANT_SOURCE_ONE_TIME))
            await session.flush()
            await session.refresh(user)
            return user

    async def transfer_balance(self, *, from_user_id: str, to_user_id: str) -> None:
        """Move all of one user's hint buckets to another (support transfer).

        Adds the donor's free/sub/paid balances onto the recipient, zeroes the
        donor, and records a transfer grant. Rows are locked in a stable id
        order to avoid deadlocks.
        """
        first, second = sorted([from_user_id, to_user_id])
        async with self._begin() as session:
            u1 = await session.get(User, first, with_for_update=True)
            u2 = await session.get(User, second, with_for_update=True)
            donor = u1 if first == from_user_id else u2
            recipient = u2 if first == from_user_id else u1
            if donor is None or recipient is None:
                raise NotFoundException("Donor or recipient user not found")

            moved = donor.free_hints + donor.sub_hints + donor.paid_hints
            recipient.free_hints += donor.free_hints
            recipient.sub_hints += donor.sub_hints
            recipient.paid_hints += donor.paid_hints
            donor.free_hints = donor.sub_hints = donor.paid_hints = 0
            now = utcnow()
            donor.updated_at = now
            recipient.updated_at = now
            if moved > 0:
                session.add(
                    HintGrant(user_id=to_user_id, amount=moved, source=GRANT_SOURCE_TRANSFER)
                )
            await session.flush()

    async def has_granted_period(self, subscription_id: str, period_key: str) -> bool:
        """True if this subscription cycle was already granted (idempotency)."""
        stmt = sa.select(HintGrant.id).where(
            HintGrant.subscription_id == subscription_id,
            HintGrant.period_key == period_key,
        )
        async with self._session() as session:
            return await session.scalar(stmt) is not None

    async def list_consumptions(
        self, user_id: str, *, limit: int, offset: int
    ) -> tuple[list[HintConsumption], int]:
        """Return a page of the user's consumption ledger plus the total count."""
        async with self._session() as session:
            total = await session.scalar(
                sa.select(sa.func.count())
                .select_from(HintConsumption)
                .where(HintConsumption.user_id == user_id)
            )
            rows = await session.execute(
                sa.select(HintConsumption)
                .where(HintConsumption.user_id == user_id)
                .order_by(HintConsumption.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(rows.scalars().all()), int(total or 0)
