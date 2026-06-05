"""Current-user profile endpoint."""

from fastapi import APIRouter, Depends

from dating.dependencies import get_current_user
from dating.models.user import User
from dating.serializers.user import UserSerializer

router = APIRouter()


@router.get("/me", response_model=UserSerializer, tags=["profile"])
async def get_me(user: User = Depends(get_current_user)) -> UserSerializer:
    """Return the authenticated user's profile and hint balance."""
    return UserSerializer.model_validate(user)
