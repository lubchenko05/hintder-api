"""Auth endpoints. Thin handlers — verification + upsert live in ``bl.auth``."""

import logging

from fastapi import APIRouter, Depends, Request, Response, status

from dating.bl import auth as bl_auth, email_link as bl_email_link
from dating.dependencies import get_db_storage, get_email_service
from dating.serializers.auth import (
    EmailLinkValidator,
    FirebaseTokenValidator,
    JWTTokenSerializer,
)
from dating.services.email import EmailService
from dating.storages import DBStorage
from dating.utils.jwt import generate_jwt_for_user

logger = logging.getLogger(__name__)

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    """Caller's IP. Behind Cloud Run the socket peer is the proxy, so the real
    address is the first hop in ``X-Forwarded-For``."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/auth/firebase", response_model=JWTTokenSerializer, tags=["auth"])
async def firebase_login(
    payload: FirebaseTokenValidator,
    request: Request,
    db: DBStorage = Depends(get_db_storage),
) -> JWTTokenSerializer:
    """Exchange a Firebase ID token for a backend JWT (creates the user if new)."""
    result = await bl_auth.verify_firebase_token_and_upsert_user(
        db,
        payload.token,
        device_id=payload.device_id,
        # Forwarded to Meta with a server-side registration event; they raise
        # match quality but are useless without the email, so they're optional.
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    access_token = generate_jwt_for_user(result.user.id, result.user.email)
    return JWTTokenSerializer(
        access_token=access_token,
        registered=result.registration_event_id is not None,
        registration_event_id=result.registration_event_id,
    )


@router.post("/auth/email-link", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"])
async def send_email_link(
    payload: EmailLinkValidator,
    email_svc: EmailService = Depends(get_email_service),
) -> Response:
    """Email a branded passwordless sign-in link (minted by Firebase, sent via Brevo)."""
    await bl_email_link.send_sign_in_email(email_svc, payload.email, payload.continue_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
