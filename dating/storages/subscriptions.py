"""Data access for ``Subscription`` rows + the user→subscription link.

Creating a subscription also points the user at it (``users.subscription_id``)
in the same transaction, since the FK lives on the user side. Re-pointing that
FK (support transfer) is a deliberate one-liner here.
"""

from datetime import datetime
from typing import Any

import sqlalchemy as sa

from dating.models.subscription import Subscription
from dating.models.user import User
from dating.storages.base import BaseStorage
from dating.utils.datetime import utcnow
from dating.utils.error_handler import NotFoundException


class SubscriptionStorage(BaseStorage):
    """Create / fetch / update subscriptions and (re)link them to users."""

    async def create_for_user(
        self,
        *,
        user_id: str,
        paddle_subscription_id: str,
        tier: str,
        billing_interval: str,
        hints_per_cycle: int,
        cap: int,
        is_unlimited: bool,
        status: str,
        paddle_customer_id: str | None = None,
    ) -> Subscription:
        """Create a subscription and point the user's FK at it (atomic)."""
        async with self._begin() as session:
            sub = Subscription(
                paddle_subscription_id=paddle_subscription_id,
                paddle_customer_id=paddle_customer_id,
                tier=tier,
                billing_interval=billing_interval,
                hints_per_cycle=hints_per_cycle,
                cap=cap,
                is_unlimited=is_unlimited,
                status=status,
            )
            session.add(sub)
            await session.flush()

            user = await session.get(User, user_id, with_for_update=True)
            if user is None:
                raise NotFoundException(f"User {user_id} not found")
            user.subscription_id = sub.id
            user.updated_at = utcnow()
            await session.flush()
            await session.refresh(sub)
            return sub

    async def get_by_id(self, sub_id: str) -> Subscription | None:
        """Return a subscription by its own id, or ``None``."""
        async with self._session() as session:
            return await session.get(Subscription, sub_id)

    async def get_by_paddle_id(self, paddle_subscription_id: str) -> Subscription | None:
        """Return a subscription by its Paddle id, or ``None``."""
        stmt = sa.select(Subscription).where(
            Subscription.paddle_subscription_id == paddle_subscription_id
        )
        async with self._session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_fields(self, sub_id: str, **fields: Any) -> Subscription:
        """Patch arbitrary columns on a subscription and return it refreshed."""
        async with self._begin() as session:
            sub = await session.get(Subscription, sub_id, with_for_update=True)
            if sub is None:
                raise NotFoundException(f"Subscription {sub_id} not found")
            for key, value in fields.items():
                setattr(sub, key, value)
            sub.updated_at = utcnow()
            await session.flush()
            await session.refresh(sub)
            return sub

    async def detach_user(self, user_id: str) -> None:
        """Clear a user's subscription pointer (on cancel)."""
        async with self._begin() as session:
            user = await session.get(User, user_id, with_for_update=True)
            if user is not None:
                user.subscription_id = None
                user.updated_at = utcnow()
                await session.flush()

    async def owner_id(self, sub_id: str) -> str | None:
        """Return the user id currently pointing at this subscription, if any."""
        stmt = sa.select(User.id).where(User.subscription_id == sub_id)
        async with self._session() as session:
            return await session.scalar(stmt)

    async def relink(self, *, sub_id: str, from_user_id: str | None, to_user_id: str) -> None:
        """Move the subscription FK from one user to another (support transfer).

        Clears the old owner's pointer (if given) and sets the new owner's, in a
        single transaction. The unique constraint guarantees one owner at a time.
        """
        async with self._begin() as session:
            if from_user_id is not None:
                old = await session.get(User, from_user_id, with_for_update=True)
                if old is not None and old.subscription_id == sub_id:
                    old.subscription_id = None
                    old.updated_at = utcnow()
                    await session.flush()
            new = await session.get(User, to_user_id, with_for_update=True)
            if new is None:
                raise NotFoundException(f"User {to_user_id} not found")
            new.subscription_id = sub_id
            new.updated_at = utcnow()
            await session.flush()

    async def list_period_due(self, now: datetime) -> list[Subscription]:
        """Return live subscriptions whose next monthly drip is due (for sync)."""
        stmt = sa.select(Subscription).where(
            Subscription.is_unlimited.is_(False),
            Subscription.paid_until.is_not(None),
            Subscription.last_accrued_at.is_not(None),
        )
        async with self._session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())
