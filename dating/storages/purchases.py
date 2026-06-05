"""Data access for ``Purchase`` rows."""

import sqlalchemy as sa

from dating.models.purchase import Purchase, PURCHASE_COMPLETED, PURCHASE_PENDING
from dating.storages.base import BaseStorage
from dating.utils.datetime import utcnow


class PurchaseStorage(BaseStorage):
    """Create + reconcile hint-pack purchases."""

    async def create_pending(
        self,
        *,
        user_id: str,
        paddle_transaction_id: str,
        pack_id: str,
        hints: int,
        amount_cents: int,
        currency: str = "USD",
    ) -> Purchase:
        """Record a not-yet-paid purchase tied to a Paddle transaction id."""
        async with self._begin() as session:
            purchase = Purchase(
                user_id=user_id,
                paddle_transaction_id=paddle_transaction_id,
                pack_id=pack_id,
                hints=hints,
                amount_cents=amount_cents,
                currency=currency,
            )
            session.add(purchase)
            await session.flush()
            await session.refresh(purchase)
            return purchase

    async def get_by_transaction_id(self, paddle_transaction_id: str) -> Purchase | None:
        """Return the purchase for a Paddle transaction id, or ``None``."""
        stmt = sa.select(Purchase).where(Purchase.paddle_transaction_id == paddle_transaction_id)
        async with self._session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def transition_to_completed(self, paddle_transaction_id: str) -> Purchase | None:
        """Atomically flip a *pending* purchase to ``completed``.

        Returns the purchase only if this call performed the transition. Returns
        ``None`` if the transaction is missing or was already completed — that's
        the idempotency guard: only the first caller credits the hints.
        """
        async with self._begin() as session:
            purchase = await session.scalar(
                sa.select(Purchase)
                .where(Purchase.paddle_transaction_id == paddle_transaction_id)
                .with_for_update()
            )
            if purchase is None or purchase.status != PURCHASE_PENDING:
                return None
            purchase.status = PURCHASE_COMPLETED
            purchase.updated_at = utcnow()
            await session.flush()
            await session.refresh(purchase)
            return purchase

    async def list_for_user(
        self, user_id: str, *, limit: int, offset: int
    ) -> tuple[list[Purchase], int]:
        """Return a page of the user's purchases (newest first) + total count."""
        async with self._session() as session:
            total = await session.scalar(
                sa.select(sa.func.count()).select_from(Purchase).where(Purchase.user_id == user_id)
            )
            rows = await session.execute(
                sa.select(Purchase)
                .where(Purchase.user_id == user_id)
                .order_by(Purchase.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(rows.scalars().all()), int(total or 0)
