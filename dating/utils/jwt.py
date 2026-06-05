"""Backend-issued JWT helpers.

After a Firebase ID token is verified we mint our own short-ish-lived JWT so
subsequent requests don't pay the Firebase round-trip. The ``sub`` claim is the
Firebase UID (also our ``User.id``).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def _get_secret_key() -> str:
    """Read the signing key from config at call time (not import time)."""
    from dating.config import get_config

    return get_config().jwt_secret_key


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Encode ``data`` into a signed JWT with an ``exp`` claim."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, _get_secret_key(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode + verify a JWT. Raise ``ValueError`` on expiry/invalidity."""
    try:
        return jwt.decode(token, _get_secret_key(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError("Invalid token") from exc


def generate_jwt_for_user(user_id: str, email: str | None) -> str:
    """Mint an access token for the given user identity."""
    return create_access_token(data={"sub": user_id, "email": email})
