"""Match archive endpoints — list / fetch / upsert / delete, scoped to the user."""

from fastapi import APIRouter, Depends, Response, status

from dating.dependencies import get_current_user, get_db_storage
from dating.models.match import Match
from dating.models.user import User
from dating.serializers.matches import MatchSerializer, MatchUpsertValidator
from dating.storages import DBStorage

router = APIRouter()


def _serialize(m: Match) -> MatchSerializer:
    """Map a ``Match`` row to the camelCase frontend shape."""
    return MatchSerializer(
        id=m.id,
        name=m.name,
        age=m.age,
        status=m.status,
        analysis=m.analysis,
        conversation=m.conversation,
        messages=m.messages,
        followUp=m.follow_up,
        pickedStyle=m.picked_style,
        pickedTone=m.picked_tone,
        createdAt=m.created_at_ms,
        updatedAt=m.updated_at_ms,
    )


@router.get("/matches", response_model=list[MatchSerializer], tags=["matches"])
async def list_matches(
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
) -> list[MatchSerializer]:
    """Return the user's matches, most-recently-updated first."""
    rows = await db.match.list_for_user(user.id)
    return [_serialize(m) for m in rows]


@router.put("/matches/{match_id}", response_model=MatchSerializer, tags=["matches"])
async def upsert_match(
    match_id: str,
    payload: MatchUpsertValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
) -> MatchSerializer:
    """Create or replace one of the user's matches."""
    match = await db.match.upsert(
        match_id,
        user.id,
        {
            "name": payload.name,
            "age": payload.age,
            "status": payload.status,
            "picked_style": payload.pickedStyle,
            "picked_tone": payload.pickedTone,
            "analysis": payload.analysis,
            "conversation": [t.model_dump() for t in payload.conversation],
            "messages": payload.messages,
            "follow_up": payload.followUp,
            "created_at_ms": payload.createdAt,
            "updated_at_ms": payload.updatedAt,
        },
    )
    return _serialize(match)


@router.delete("/matches/{match_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["matches"])
async def delete_match(
    match_id: str,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
) -> Response:
    """Permanently delete one of the user's matches."""
    await db.match.delete(match_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
