"""Firebase Admin SDK wrapper — verify client ID tokens.

Initialisation is idempotent and lazy: the Admin app is created on first use
from the configured service-account file, or from Application Default
Credentials when no file is set. Verification failures surface as
``UnauthorizedException`` so the global handler maps them to HTTP 401.
"""

import logging
from typing import Any

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials

from dating.config import get_config
from dating.utils.error_handler import UnauthorizedException

logger = logging.getLogger(__name__)

_firebase_app: firebase_admin.App | None = None


def _get_firebase_app() -> firebase_admin.App:
    """Return the initialised Firebase Admin app, creating it once."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    try:
        _firebase_app = firebase_admin.get_app()
        return _firebase_app
    except ValueError:
        pass
    cfg = get_config()
    # Pin the project explicitly so ID-token verification checks the ``aud``
    # claim against ``firebase_project_id`` — NOT whatever project the service
    # account happens to belong to. Token verification only needs the project
    # id + Google's public keys, so this works even if the SA is from another
    # project (and gives a clear, correct audience check either way).
    options = {"projectId": cfg.firebase_project_id} if cfg.firebase_project_id else None
    if cfg.firebase_credentials_file:
        cred = credentials.Certificate(cfg.firebase_credentials_file)
        _firebase_app = firebase_admin.initialize_app(cred, options)
    else:
        # Application Default Credentials (e.g. on Cloud Run).
        _firebase_app = firebase_admin.initialize_app(options=options)
    return _firebase_app


def verify_id_token(token: str) -> dict[str, Any]:
    """Verify a Firebase ID token; return its decoded claims or raise 401."""
    _get_firebase_app()
    try:
        return firebase_auth.verify_id_token(token)
    except firebase_admin.exceptions.FirebaseError as exc:
        raise UnauthorizedException(f"Invalid Firebase token: {exc}") from exc
    except Exception as exc:
        raise UnauthorizedException(f"Token verification failed: {exc}") from exc


def generate_email_sign_in_link(email: str, continue_url: str) -> str:
    """Mint a passwordless email sign-in link for ``email`` (handled in-app).

    Requires the Email-link sign-in provider to be enabled for the project and
    ``continue_url``'s domain to be in the authorised domains list. We send this
    link ourselves (branded email) instead of letting Firebase mail it.
    """
    _get_firebase_app()
    settings = firebase_auth.ActionCodeSettings(url=continue_url, handle_code_in_app=True)
    return firebase_auth.generate_sign_in_with_email_link(email, action_code_settings=settings)
