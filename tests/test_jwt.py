"""Tests for backend JWT minting/decoding."""

from datetime import timedelta

import pytest

from dating.utils.jwt import (
    create_access_token,
    decode_access_token,
    generate_jwt_for_user,
)


def test_roundtrip_carries_claims() -> None:
    token = generate_jwt_for_user("uid_123", "a@b.com")
    payload = decode_access_token(token)
    assert payload["sub"] == "uid_123"
    assert payload["email"] == "a@b.com"


def test_expired_token_rejected() -> None:
    token = create_access_token({"sub": "uid"}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(ValueError):
        decode_access_token(token)


def test_garbage_token_rejected() -> None:
    with pytest.raises(ValueError):
        decode_access_token("not.a.jwt")
