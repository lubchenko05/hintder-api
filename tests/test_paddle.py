"""Tests for the Paddle service — mock checkout + signature verification."""

import hashlib
import hmac

import pytest

from dating.config import Config
from dating.services.paddle import PaddleService


@pytest.mark.asyncio
async def test_mock_checkout_points_at_frontend() -> None:
    cfg = Config(frontend_base_url="http://localhost:3000", paddle_api_key="")
    service = PaddleService(cfg)
    session = await service.create_checkout(hints=5, price_usd=2.99, customer_email="a@b.com")
    assert session.is_mock is True
    assert session.hints == 5
    # Relative URL so it resolves on whatever origin/port the SPA runs on.
    assert session.checkout_url.startswith("/checkout/mock")
    assert session.transaction_id in session.checkout_url


def test_signature_rejected_without_secret() -> None:
    cfg = Config(paddle_webhook_secret="")
    service = PaddleService(cfg)
    assert service.verify_webhook_signature(b"{}", "ts=1;h1=abc") is False


def test_signature_roundtrip() -> None:
    secret = "whsec_test"
    cfg = Config(paddle_webhook_secret=secret)
    service = PaddleService(cfg)
    body = b'{"event_id":"evt_1"}'
    ts = "1700000000"
    digest = hmac.new(secret.encode(), f"{ts}:{body.decode()}".encode(), hashlib.sha256).hexdigest()
    assert service.verify_webhook_signature(body, f"ts={ts};h1={digest}") is True
    assert service.verify_webhook_signature(body, f"ts={ts};h1=deadbeef") is False
