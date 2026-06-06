"""Telegram operator alerts.

A tiny, dependency-light notifier: it POSTs to the Telegram Bot API to ping the
operator's chat(s) when something worth knowing happens — a real registration or
a new paid subscription. Everything here is best-effort: callers wrap invocations
so a Telegram outage never breaks the user-facing request.

Only ``telegram_bot_token`` (a Secret Manager secret) is configurable; the
destination is hard-pinned to ``TELEGRAM_OPERATOR_CHAT_ID`` so alerts can never
be redirected. When the token is missing, ``telegram_enabled`` is False and every
send is a silent no-op.
"""

import logging

import httpx

from dating.config import get_config

logger = logging.getLogger(__name__)


def _api_url() -> str:
    """Base Bot API URL for the configured token."""
    return f"https://api.telegram.org/bot{get_config().telegram_bot_token.strip()}"


async def _send_message(chat_id: str, text: str) -> bool:
    """POST one HTML message to a single chat; never raises."""
    if not get_config().telegram_enabled:
        logger.warning("Telegram not configured, skipping alert")
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_api_url()}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
        if resp.status_code == 200:
            return True
        logger.error("Telegram error %s for chat %s: %s", resp.status_code, chat_id, resp.text)
        return False
    except Exception:
        logger.exception("Failed to send Telegram message to %s", chat_id)
        return False


async def send_alert(text: str) -> None:
    """Fan a message out to every configured alert chat."""
    for chat_id in get_config().telegram_chat_ids_list:
        await _send_message(chat_id, text)


async def notify_new_user(email: str | None, name: str | None) -> None:
    """Operator ping when a user first becomes a real (named/emailed) account."""
    display = email or name or "unknown"
    await send_alert(f"👤 <b>New user registered</b>\n\n{display}")


async def notify_subscription_created(email: str | None, plan: str, subscription_id: str) -> None:
    """Operator ping when a brand-new subscription is activated."""
    display = email or "unknown"
    await send_alert(f"💰 <b>New subscription</b>\n\n👤 {display}\n📦 {plan}\n🔑 {subscription_id}")
