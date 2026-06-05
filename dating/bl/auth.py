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
        return await db.user.create(
            uid,
            email=email,
            name=name,
            avatar=avatar,
            free_hints=grant,
            device_id=device_id,
        )

    # Refresh mutable identity fields only if the token carries fresher values.
    updates: dict[str, str | None] = {}
    if email is not None and email != existing.email:
        updates["email"] = email
    if name is not None and name != existing.name:
        updates["name"] = name
    if avatar is not None and avatar != existing.avatar:
        updates["avatar"] = avatar
    if updates:
        refreshed = await db.user.update(uid, updates)
        if refreshed is not None:
            return refreshed
    return existing
