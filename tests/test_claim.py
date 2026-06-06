"""Tests for the hardened anonymous-asset claim.

``claim_anonymous_assets`` is frontend-triggered, so it must be defensive. These
tests pin the two security guards (donor must be anonymous; recipient must not
already pay) and the happy path, using lightweight mocks instead of a DB — the
branch logic is what matters here, not the storage layer.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dating.bl import billing


def _user(
    uid: str,
    *,
    email: str | None = None,
    subscription_id: str | None = None,
    free: int = 0,
    sub: int = 0,
    paid: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uid,
        email=email,
        subscription_id=subscription_id,
        free_hints=free,
        sub_hints=sub,
        paid_hints=paid,
        total_hints=free + sub + paid,
    )


def _db(users: dict[str, SimpleNamespace], *, live_sub: bool = False) -> SimpleNamespace:
    async def get_by_id(uid: str) -> SimpleNamespace | None:
        return users.get(uid)

    return SimpleNamespace(
        user=SimpleNamespace(get_by_id=AsyncMock(side_effect=get_by_id)),
        subscription=SimpleNamespace(
            get_by_id=AsyncMock(return_value=SimpleNamespace(is_live=live_sub))
        ),
        hint=SimpleNamespace(transfer_balance=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_claim_refuses_permanent_donor(monkeypatch: pytest.MonkeyPatch) -> None:
    """A donor WITH an email is a permanent account and must never be drained."""
    reattach = AsyncMock()
    monkeypatch.setattr(billing, "reattach_subscription", reattach)
    donor = _user("permA", email="a@b.com", subscription_id="sub1")
    recipient = _user("permB", email="b@b.com")
    db = _db({"permA": donor, "permB": recipient})

    await billing.claim_anonymous_assets(db, prev_user_id="permA", to_user_id="permB")

    reattach.assert_not_called()
    db.hint.transfer_balance.assert_not_called()


@pytest.mark.asyncio
async def test_claim_refuses_when_recipient_already_pays(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never move a subscription onto an account that already has a live one."""
    reattach = AsyncMock()
    monkeypatch.setattr(billing, "reattach_subscription", reattach)
    donor = _user("anonX", email=None, subscription_id="sub1")
    recipient = _user("permB", email="b@b.com", subscription_id="subR")
    db = _db({"anonX": donor, "permB": recipient}, live_sub=True)

    await billing.claim_anonymous_assets(db, prev_user_id="anonX", to_user_id="permB")

    reattach.assert_not_called()


@pytest.mark.asyncio
async def test_claim_moves_subscription_from_anonymous_donor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: anon donor's sub moves to a recipient that doesn't yet pay."""
    reattach = AsyncMock()
    monkeypatch.setattr(billing, "reattach_subscription", reattach)
    donor = _user("anonX", email=None, subscription_id="sub1")
    recipient = _user("permB", email="b@b.com", subscription_id=None)
    db = _db({"anonX": donor, "permB": recipient})

    await billing.claim_anonymous_assets(db, prev_user_id="anonX", to_user_id="permB")

    reattach.assert_awaited_once_with(db, sub_id="sub1", to_user_id="permB")


@pytest.mark.asyncio
async def test_claim_transfers_hints_when_donor_has_no_subscription() -> None:
    """Anon donor with only a hint balance → hints move, no subscription needed."""
    donor = _user("anonX", email=None, subscription_id=None, free=3)
    recipient = _user("permB", email="b@b.com", subscription_id=None)
    db = _db({"anonX": donor, "permB": recipient})

    await billing.claim_anonymous_assets(db, prev_user_id="anonX", to_user_id="permB")

    db.hint.transfer_balance.assert_awaited_once_with(from_user_id="anonX", to_user_id="permB")


@pytest.mark.asyncio
async def test_claim_noop_when_same_uid() -> None:
    """Linking preserved the uid → nothing to move."""
    user = _user("u1", email=None, subscription_id="sub1")
    db = _db({"u1": user})

    await billing.claim_anonymous_assets(db, prev_user_id="u1", to_user_id="u1")

    db.user.get_by_id.assert_not_called()
    db.hint.transfer_balance.assert_not_called()
