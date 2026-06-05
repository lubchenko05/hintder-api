"""Paddle billing service — mocked checkout + real signature verification.

hintder sells one-time hint packs (no subscriptions), so this is intentionally
small: create a checkout for a pack, and verify inbound webhook signatures.
While ``cfg.paddle_enabled`` is False the checkout is mocked — it points the
browser at the frontend's local checkout page, and a dev-only "simulate
webhook" endpoint grants the hints. Swap in the real Paddle SDK behind the same
method signatures when live IDs exist.
"""

import hashlib
import hmac
import logging
import uuid

from pydantic import BaseModel

from dating.config import Config

logger = logging.getLogger(__name__)


class CheckoutSession(BaseModel):
    """A created checkout: where to send the browser + the txn we will reconcile."""

    transaction_id: str
    checkout_url: str
    hints: int
    price_usd: float
    is_mock: bool


class PaddleService:
    """Thin wrapper over Paddle. Mock path active until an API key is set."""

    def __init__(self, cfg: Config) -> None:
        """Capture config; no network clients are created until needed."""
        self._cfg = cfg

    @property
    def enabled(self) -> bool:
        """True when a real Paddle API key is configured."""
        return self._cfg.paddle_enabled

    async def create_checkout(
        self,
        *,
        hints: int,
        price_usd: float,
        customer_email: str | None,
    ) -> CheckoutSession:
        """Create a checkout session for a hint pack.

        Mock mode returns a *relative* URL to the frontend checkout page (so it
        resolves on whatever origin/port the SPA runs on — no port mismatch);
        the real path would open a Paddle hosted/overlay checkout.
        """
        transaction_id = f"txn_{uuid.uuid4().hex[:24]}"
        if not self.enabled:
            url = f"/checkout/mock?txn={transaction_id}&hints={hints}&price={price_usd}"
            return CheckoutSession(
                transaction_id=transaction_id,
                checkout_url=url,
                hints=hints,
                price_usd=price_usd,
                is_mock=True,
            )
        # Real Paddle checkout creation plugs in here.
        raise NotImplementedError("Real Paddle checkout not yet wired.")

    async def create_subscription_checkout(
        self,
        *,
        plan_id: str,
        price_usd: float,
        hints_per_cycle: int,
        customer_email: str | None,
    ) -> CheckoutSession:
        """Create a checkout for a subscription plan (mock until Paddle is live).

        The transaction id doubles as the mock ``paddle_subscription_id`` we
        reconcile on completion. ``hints`` carries the per-cycle allotment so the
        mock checkout page can show it.
        """
        subscription_id = f"sub_{uuid.uuid4().hex[:24]}"
        if not self.enabled:
            url = (
                f"/checkout/mock?txn={subscription_id}"
                f"&plan={plan_id}&price={price_usd}&kind=sub"
            )
            return CheckoutSession(
                transaction_id=subscription_id,
                checkout_url=url,
                hints=hints_per_cycle,
                price_usd=price_usd,
                is_mock=True,
            )
        raise NotImplementedError("Real Paddle subscription checkout not yet wired.")

    def verify_webhook_signature(self, raw_body: bytes, signature_header: str) -> bool:
        """Verify a ``Paddle-Signature: ts=<ts>;h1=<hex>`` HMAC-SHA256 header."""
        secret = self._cfg.paddle_webhook_secret
        if not signature_header or not secret:
            return False
        try:
            parts: dict[str, str] = {}
            for item in signature_header.split(";"):
                key, value = item.split("=", 1)
                parts[key.strip()] = value.strip()
            ts, h1 = parts.get("ts", ""), parts.get("h1", "")
            if not ts or not h1:
                return False
            signed = f"{ts}:{raw_body.decode('utf-8')}"
            expected = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, h1)
        except Exception:
            logger.exception("Failed to verify Paddle signature")
            return False
