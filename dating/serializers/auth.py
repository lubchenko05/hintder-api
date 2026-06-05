"""Auth endpoint request validators + response serializers."""

from dating.serializers.base import BaseSerializer, BaseValidator
from dating.validators import NonEmptyStr


class FirebaseTokenValidator(BaseValidator):
    """``POST /auth/firebase`` body — a Firebase ID token from the client SDK."""

    token: NonEmptyStr
    # Stable per-browser id (localStorage) so free hints are granted once per
    # device, not once per (re-creatable) anonymous account.
    device_id: str | None = None


class JWTTokenSerializer(BaseSerializer):
    """``POST /auth/firebase`` response — the backend-issued bearer JWT."""

    access_token: str
    token_type: str = "bearer"
