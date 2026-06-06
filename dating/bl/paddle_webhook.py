"""Paddle webhook handling — verify, deduplicate, and grant hints.

The real grant path. Verifies the HMAC signature, records the event for
idempotency, and on ``transaction.completed`` credits the matching purchase via
the shared ``billing.grant_purchase``. Mocked checkouts don't hit this — they
use the dev mock-complete endpoint — but the handler is correct for go-live.
"""

import json
import logging
from typing import Any

from dating.bl import billing as bl_billing
from dating.config import get_config
from dating.services.paddle import PaddleService
from dating.storages import DBStorage
from dating.utils.error_handler import BadRequestException, UnauthorizedException

logger = logging.getLogger(__name__)

EVENT_TRANSACTION_COMPLETED = "transaction.completed"
EVENT_SUB_ACTIVATED = "subscription.activated"
EVENT_SUB_UPDATED = "subscription.updated"
EVENT_SUB_CANCELED = "subscription.canceled"


async def _activate_from_subscription_data(
    db: DBStorage, data: dict[str, Any], event_id: str
) -> None:
    """Resolve uid + plan from a subscription event and activate it (idempotent)."""
    paddle_sub_id = data.get("id")
    custom = data.get("custom_data") or {}
    user_id = custom.get("uid")
    items = data.get("items") or []
    price_id = (items[0].get("price") or {}).get("id") if items else None
    plan_id = get_config().plan_id_for_price(price_id or "") or custom.get("plan_id")
    if not (paddle_sub_id and user_id and plan_id):
        logger.warning(
            "subscription event %s missing data (sub=%s uid=%s plan=%s)",
            event_id, paddle_sub_id, user_id, plan_id,
        )
        return
    await bl_billing.activate_subscription_from_webhook(
        db,
        paddle_subscription_id=paddle_sub_id,
        user_id=user_id,
        plan_id=plan_id,
        paddle_customer_id=data.get("customer_id"),
    )


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

    data = payload.get("data") or {}
    if event_type == EVENT_TRANSACTION_COMPLETED:
        transaction_id = data.get("id")
        if transaction_id:
            await bl_billing.grant_purchase(db, transaction_id)
        else:
            logger.warning("transaction.completed without a transaction id: %s", event_id)
    elif event_type in (EVENT_SUB_ACTIVATED, EVENT_SUB_UPDATED):
        await _activate_from_subscription_data(db, data, event_id)
    elif event_type == EVENT_SUB_CANCELED:
        sub_id = data.get("id")
        if sub_id:
            await bl_billing.cancel_subscription_from_webhook(db, paddle_subscription_id=sub_id)

    await db.paddle_event.mark_processed(event_id)
