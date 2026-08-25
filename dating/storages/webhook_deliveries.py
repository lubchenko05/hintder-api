"""Data access for inbound webhook deliveries (dedup + audit)."""

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from dating.models.webhook_delivery import WebhookDelivery
from dating.storages.base import BaseStorage


class WebhookDeliveryStorage(BaseStorage):
    """Record deliveries; the unique key is the deduplication."""

    async def get(self, provider: str, delivery_id: str) -> WebhookDelivery | None:
        """The earlier record of this delivery, if we've seen it."""
        stmt = sa.select(WebhookDelivery).where(
            WebhookDelivery.provider == provider,
            WebhookDelivery.delivery_id == delivery_id,
        )
        async with self._session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def record(
        self,
        *,
        provider: str,
        delivery_id: str,
        event_type: str,
        body_sha256: str,
        status: str,
        error: str | None = None,
        post_id: int | None = None,
    ) -> WebhookDelivery | None:
        """Insert the delivery row; ``None`` when a concurrent retry beat us.

        The unique constraint is the arbiter under a race: two simultaneous
        retries of one delivery cannot both insert, so exactly one processes
        and the loser reports ``duplicate``.
        """
        row = WebhookDelivery(
            provider=provider,
            delivery_id=delivery_id,
            event_type=event_type,
            body_sha256=body_sha256,
            status=status,
            error=error,
            post_id=post_id,
        )
        try:
            async with self._begin() as session:
                session.add(row)
                await session.flush()
                await session.refresh(row)
                return row
        except IntegrityError:
            return None

    async def update_status(
        self, row_id: int, *, status: str, error: str | None = None, post_id: int | None = None
    ) -> None:
        """Finalise a delivery row after processing."""
        async with self._begin() as session:
            row = await session.get(WebhookDelivery, row_id)
            if row is not None:
                row.status = status
                row.error = error
                if post_id is not None:
                    row.post_id = post_id
