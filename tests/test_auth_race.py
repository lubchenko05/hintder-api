"""Two ``/auth/firebase`` calls racing for the same brand-new user.

A browser routinely has several of these in flight at once — a retry, a second
tab, a re-fired auth listener. They all read "no such user" before any of them
inserts. The insert is now idempotent, so the loser reads the winner's row
instead of raising; these tests pin the part that idempotency alone does not
buy — that the loser stays quiet. Announcing the registration twice would page
the operator twice and bill Meta for a conversion that happened once.

Mocks rather than a DB: the branch taken is what matters here.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from dating.bl import auth as bl_auth

UID = "firebase-uid-1"
EMAIL = "someone@example.com"


def _user(email: str | None) -> SimpleNamespace:
    return SimpleNamespace(id=UID, email=email, name=None, avatar=None)


def _db(*, get_or_create: tuple[SimpleNamespace, bool]) -> SimpleNamespace:
    user = SimpleNamespace(
        get_by_id=AsyncMock(return_value=None),
        device_has_grant=AsyncMock(return_value=False),
        get_or_create=AsyncMock(return_value=get_or_create),
        update=AsyncMock(return_value=get_or_create[0]),
    )
    return SimpleNamespace(user=user)


@pytest.mark.asyncio
async def test_winner_announces_the_registration() -> None:
    db = _db(get_or_create=(_user(EMAIL), True))
    with (
        patch.object(bl_auth, "verify_id_token", return_value={"uid": UID, "email": EMAIL}),
        patch.object(bl_auth, "_on_registration", new=AsyncMock()) as announced,
    ):
        result = await bl_auth.verify_firebase_token_and_upsert_user(db, "token")

    announced.assert_awaited_once()
    assert result.registration_event_id is not None
    # The id we hand the browser must be the one we reported to Meta, or the
    # pixel copy of this event is counted as a second conversion.
    assert announced.await_args.kwargs["event_id"] == result.registration_event_id


@pytest.mark.asyncio
async def test_loser_stays_quiet_but_still_gets_a_session() -> None:
    """The row the winner wrote already carries the email, so this is not a
    registration — and the request must still succeed rather than 500."""
    db = _db(get_or_create=(_user(EMAIL), False))
    with (
        patch.object(bl_auth, "verify_id_token", return_value={"uid": UID, "email": EMAIL}),
        patch.object(bl_auth, "_on_registration", new=AsyncMock()) as announced,
    ):
        result = await bl_auth.verify_firebase_token_and_upsert_user(db, "token")

    announced.assert_not_awaited()
    assert result.registration_event_id is None
    assert result.user.id == UID
