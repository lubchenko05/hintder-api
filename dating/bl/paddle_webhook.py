"""Paddle webhook handling — verify, deduplicate, and grant hints.

The real grant path. Verifies the HMAC signature, records the event for
idempotency, and on ``transaction.completed`` credits the matching purchase via
the shared ``billing.grant_purchase``. Mocked checkouts don't hit this — they
use the dev mock-complete endpoint — but the handler is correct for go-live.
"""

import json
import logging
from typing import Any

from dating.bl.billing import grant_purchase
from dating.services.paddle import PaddleService
from dating.storages import DBStorage
from dating.utils.error_handler import BadRequestException, UnauthorizedException

logger = logging.getLogger(__name__)

EVENT_TRANSACTION_COMPLETED = "transaction.completed"


async def handle_webhook(
    db: DBStorage,
    paddle: PaddleService,
    *,
    raw_body: bytes,
    signature_header: str,
) -> None:
    """Verify + process one Paddle webhook delivery (idempotent)."""
    if not paddle.verify_webhook_signature(raw_body, signature_header):
        raise UnauthorizedException("Invalid Paddle signature")

    try:
        payload: dict[str, Any] = json.loads(raw_body.decode("utf-8"))
    except ValueError as exc:
        # UnicodeDecodeError + JSON errors are both ValueError subclasses.
        raise BadRequestException("Malformed webhook body") from exc

    event_id = payload.get("event_id")
    event_type = payload.get("event_type", "")
    if not event_id:
        raise BadRequestException("Missing event_id")

    # Idempotency — skip events we've already fully processed.
    existing = await db.paddle_event.get_by_event_id(event_id)
    if existing is not None and existing.processed:
        logger.info("Paddle event %s already processed; skipping", event_id)
        return
    if existing is None:
        await db.paddle_event.record(event_id=event_id, event_type=event_type, payload=payload)

    if event_type == EVENT_TRANSACTION_COMPLETED:
        transaction_id = (payload.get("data") or {}).get("id")
        if transaction_id:
            await grant_purchase(db, transaction_id)
        else:
            logger.warning("transaction.completed without a transaction id: %s", event_id)

    await db.paddle_event.mark_processed(event_id)
