"""Data access for the ``paddle_events`` idempotency log."""

import sqlalchemy as sa

from dating.models.paddle_event import PaddleEvent
from dating.storages.base import BaseStorage


class PaddleEventStorage(BaseStorage):
    """Record + look up inbound Paddle webhook events."""

    async def get_by_event_id(self, event_id: str) -> PaddleEvent | None:
        """Return the recorded event for ``event_id``, or ``None``."""
        stmt = sa.select(PaddleEvent).where(PaddleEvent.event_id == event_id)
        async with self._session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def record(
        self, *, event_id: str, event_type: str, payload: dict[str, object]
    ) -> PaddleEvent:
        """Insert a freshly received (unprocessed) event."""
        async with self._begin() as session:
            event = PaddleEvent(event_id=event_id, event_type=event_type, payload=payload)
            session.add(event)
            await session.flush()
            await session.refresh(event)
            return event

    async def mark_processed(self, event_id: str) -> None:
        """Flag the event as fully handled so re-deliveries are skipped."""
        async with self._begin() as session:
            await session.execute(
                sa.update(PaddleEvent)
                .where(PaddleEvent.event_id == event_id)
                .values(processed=True)
            )
