"""Auth dependencies — decode the backend JWT and resolve the current user."""

from typing import TYPE_CHECKING

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from dating.dependencies.inj import get_db_storage
from dating.utils.error_handler import UnauthorizedException
from dating.utils.jwt import decode_access_token

if TYPE_CHECKING:
    from dating.models.user import User
    from dating.storages import DBStorage

# auto_error=False so we raise our own ``UnauthorizedException`` (uniform 401
# JSON) instead of FastAPI's default ``HTTPException``.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/firebase", auto_error=False)


def get_current_user_id(token: str | None = Depends(oauth2_scheme)) -> str:
    """Decode the Bearer JWT and return its ``sub`` (the user id); 401 on failure."""
    if not token:
        raise UnauthorizedException("Not authenticated")
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise UnauthorizedException(str(exc)) from exc
    user_id = payload.get("sub")
    if user_id is None:
        raise UnauthorizedException("Could not validate credentials")
    return user_id


def get_optional_current_user_id(token: str | None = Depends(oauth2_scheme)) -> str | None:
    """Like :func:`get_current_user_id` but returns ``None`` instead of raising."""
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except ValueError:
        return None
    return payload.get("sub")


async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: "DBStorage" = Depends(get_db_storage),
) -> "User":
    """Resolve the JWT subject to a full ``User`` row; 401 if it no longer exists."""
    user = await db.user.get_by_id(user_id)
    if user is None:
        raise UnauthorizedException("User not found")
    return user
