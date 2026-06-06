"""Auth business logic: verify a Firebase token and upsert the user row."""

import logging

from dating.config import get_config
from dating.models.user import User
from dating.services.firebase import verify_id_token
from dating.storages import DBStorage

logger = logging.getLogger(__name__)


async def verify_firebase_token_and_upsert_user(
    db: DBStorage, token: str, device_id: str | None = None
) -> User:
    """Verify a Firebase ID token; create the user on first login else refresh.

    New users receive the configured free-hint grant — but only ONCE per device:
    if an account was already created on this ``device_id`` (e.g. the user logged
    out and a fresh anonymous account was bootstrapped on the same browser), the
    grant is 0 so the free hints can't be farmed by re-authenticating. Returning
    users get their email/name/avatar refreshed from the latest token claims,
    without touching their hint balance.
    """
    decoded = verify_id_token(token)
    uid: str = decoded["uid"]
    email: str | None = decoded.get("email")
    name: str | None = decoded.get("name")
    avatar: str | None = decoded.get("picture")

    existing = await db.user.get_by_id(uid)
    if existing is None:
        cfg = get_config()
        grant = cfg.free_hints_grant
        if device_id and await db.user.device_has_grant(device_id):
            logger.info("Device %s already claimed free hints — granting 0 to %s", device_id, uid)
            grant = 0
        logger.info("Creating new user %s (grant=%d)", uid, grant)
        created = await db.user.create(
            uid,
            email=email,
            name=name,
            avatar=avatar,
            free_hints=grant,
            device_id=device_id,
        )
        # Only ping the operator for a REAL registration — a fresh row that
        # already carries an email (e.g. signing into an existing account on a
        # new device). Anonymous bootstrap rows have no email and stay silent;
        # the anon→permanent upgrade is alerted in the refresh branch below.
        if email is not None:
            await _notify_registration(email=email, name=name)
        return created

    # The anon→permanent upgrade lands here: the row was created anonymously
    # (no email) and now the linked token carries one. That first-email moment
    # is the real "registration" in our anonymous-first model.
    is_registration = existing.email is None and email is not None

    # Refresh mutable identity fields only if the token carries fresher values.
    updates: dict[str, str | None] = {}
    if email is not None and email != existing.email:
        updates["email"] = email
    if name is not None and name != existing.name:
        updates["name"] = name
    if avatar is not None and avatar != existing.avatar:
        updates["avatar"] = avatar
    result = existing
    if updates:
        refreshed = await db.user.update(uid, updates)
        if refreshed is not None:
            result = refreshed
    if is_registration:
        await _notify_registration(email=email, name=name)
    return result


async def _notify_registration(*, email: str | None, name: str | None) -> None:
    """Best-effort operator alert on a new registration (never raises)."""
    try:
        # Local import: breaks the bl→services cycle and defers httpx.
        from dating.services.telegram import notify_new_user

        await notify_new_user(email=email, name=name)
    except Exception:
        logger.exception("Failed to send Telegram alert for new user")
