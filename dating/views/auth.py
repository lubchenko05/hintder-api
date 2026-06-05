"""Auth endpoints. Thin handlers — verification + upsert live in ``bl.auth``."""

import logging

from fastapi import APIRouter, Depends

from dating.bl import auth as bl_auth
from dating.dependencies import get_db_storage
from dating.serializers.auth import FirebaseTokenValidator, JWTTokenSerializer
from dating.storages import DBStorage
from dating.utils.jwt import generate_jwt_for_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/auth/firebase", response_model=JWTTokenSerializer, tags=["auth"])
async def firebase_login(
    payload: FirebaseTokenValidator,
    db: DBStorage = Depends(get_db_storage),
) -> JWTTokenSerializer:
    """Exchange a Firebase ID token for a backend JWT (creates the user if new)."""
    user = await bl_auth.verify_firebase_token_and_upsert_user(db, payload.token)
    access_token = generate_jwt_for_user(user.id, user.email)
    return JWTTokenSerializer(access_token=access_token)
