"""Auth endpoint request validators + response serializers."""

from pydantic import EmailStr

from dating.serializers.base import BaseSerializer, BaseValidator
from dating.validators import NonEmptyStr


class FirebaseTokenValidator(BaseValidator):
    """``POST /auth/firebase`` body — a Firebase ID token from the client SDK."""

    token: NonEmptyStr
    # Stable per-browser id (localStorage) so free hints are granted once per
    # device, not once per (re-creatable) anonymous account.
    device_id: str | None = None


class EmailLinkValidator(BaseValidator):
    """``POST /auth/email-link`` body — send a passwordless sign-in link."""

    email: EmailStr
    continue_url: NonEmptyStr


class JWTTokenSerializer(BaseSerializer):
    """``POST /auth/firebase`` response — the backend-issued bearer JWT."""

    access_token: str
    token_type: str = "bearer"
    # Whether this exchange was the moment the user registered, and the id the
    # server used when reporting it to Meta. The browser fires the same pixel
    # event with this id so the two are deduplicated rather than double-counted.
    registered: bool = False
    registration_event_id: str | None = None
