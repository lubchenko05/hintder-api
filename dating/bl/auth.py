"""Auth business logic: verify a Firebase token and upsert the user row."""

import logging

from dating.config import get_config
from dating.models.user import User
from dating.services.firebase import verify_id_token
from dating.storages import DBStorage

logger = logging.getLogger(__name__)


async def verify_firebase_token_and_upsert_user(db: DBStorage, token: str) -> User:
    """Verify a Firebase ID token; create the user on first login else refresh.

    New users receive the configured free-hint grant. Returning users get their
    email/name/avatar refreshed from the latest token claims (kept current with
    whatever the provider sends), without touching their hint balance.
    """
    decoded = verify_id_token(token)
    uid: str = decoded["uid"]
    email: str | None = decoded.get("email")
    name: str | None = decoded.get("name")
    avatar: str | None = decoded.get("picture")

    existing = await db.user.get_by_id(uid)
    if existing is None:
        cfg = get_config()
        logger.info("Creating new user %s", uid)
        return await db.user.create(
            uid,
            email=email,
            name=name,
            avatar=avatar,
            free_hints=cfg.free_hints_grant,
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
