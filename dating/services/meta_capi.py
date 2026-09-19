"""Meta Conversions API — server-side conversion events.

The browser pixel is not a reliable place to report a registration. It fires
from an auth listener that only recognises a sign-up when it saw the anonymous
session first, in the same page load; it is also the first thing an ad blocker
or a tracking-prevention setting removes. The first live campaign proved the
point: two real registrations happened and Meta recorded zero, so the campaign
optimising for that event had nothing to learn from.

The backend knows the truth — it is the thing that creates the account — so it
reports the event itself. Browser-side events keep firing too; Meta dedupes on
``event_id`` when both arrive.
"""

import hashlib
import logging
import time
import uuid

import httpx

from dating.config import get_config

logger = logging.getLogger(__name__)

_GRAPH = "https://graph.facebook.com/v21.0"

EVENT_COMPLETE_REGISTRATION = "CompleteRegistration"


def _hashed(value: str | None) -> str | None:
    """Meta requires user identifiers pre-hashed: lowercase, trimmed, SHA-256."""
    if not value:
        return None
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


async def send_event(
    event_name: str,
    *,
    email: str | None = None,
    event_id: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    event_source_url: str | None = None,
) -> bool:
    """Post one conversion event. Best effort — never raises, never blocks a signup.

    Returns whether Meta accepted it, so callers can log the difference between
    "we chose not to send" and "we sent and it failed".
    """
    cfg = get_config()
    if not cfg.meta_capi_token or not cfg.meta_dataset_id:
        return False

    user_data: dict[str, object] = {}
    if (em := _hashed(email)) is not None:
        user_data["em"] = [em]
    # Not hashed — Meta matches on these directly, and they only help when the
    # event came from a real request rather than a background job.
    if client_ip:
        user_data["client_ip_address"] = client_ip
    if user_agent:
        user_data["client_user_agent"] = user_agent
    if not user_data:
        logger.info("CAPI %s skipped — nothing to match on", event_name)
        return False

    payload = {
        "data": [
            {
                "event_name": event_name,
                "event_time": int(time.time()),
                # Shared with the browser event so Meta counts one conversion.
                "event_id": event_id or uuid.uuid4().hex,
                "action_source": "website",
                "event_source_url": event_source_url or cfg.frontend_base_url,
                "user_data": user_data,
            }
        ]
    }
    url = f"{_GRAPH}/{cfg.meta_dataset_id}/events?access_token={cfg.meta_capi_token}"
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code >= 300:
            logger.error("CAPI %s rejected (%s): %s", event_name, resp.status_code, resp.text[:300])
            return False
        return True
    except Exception:
        logger.exception("CAPI %s failed to send", event_name)
        return False
