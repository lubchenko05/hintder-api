"""Match archive endpoints — list / fetch / upsert / delete, scoped to the user."""

import asyncio

from fastapi import APIRouter, Depends, Response, status

from dating.dependencies import get_current_user, get_db_storage, get_storage_service
from dating.models.match import Match
from dating.models.user import User
from dating.serializers.matches import MatchSerializer, MatchUpsertValidator
from dating.services.storage import StorageService
from dating.storages import DBStorage

router = APIRouter()


async def _serialize(m: Match, user_id: str, storage: StorageService) -> MatchSerializer:
    """Map a ``Match`` row to the camelCase frontend shape.

    Screenshots are stored as private ``gs://`` URIs inside ``analysis``; we
    exchange them for short-lived signed view URLs here so the client can show
    the real photo immediately on resume — no extra round-trip, no placeholder
    flash. The canonical ``gs://`` URIs stay untouched in ``analysis``.
    """
    uris = m.analysis.get("imageUrls") or [] if isinstance(m.analysis, dict) else []
    signed = await storage.signed_urls(user_id=user_id, uris=uris) if uris else []
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
        imageUrls=signed,
    )


@router.get("/matches", response_model=list[MatchSerializer], tags=["matches"])
async def list_matches(
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
    storage: StorageService = Depends(get_storage_service),
) -> list[MatchSerializer]:
    """Return the user's matches, most-recently-updated first."""
    rows = await db.match.list_for_user(user.id)
    # Sign each match's screenshots concurrently so total latency is the slowest
    # single match, not the sum.
    return list(await asyncio.gather(*(_serialize(m, user.id, storage) for m in rows)))


@router.put("/matches/{match_id}", response_model=MatchSerializer, tags=["matches"])
async def upsert_match(
    match_id: str,
    payload: MatchUpsertValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
    storage: StorageService = Depends(get_storage_service),
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
    return await _serialize(match, user.id, storage)


@router.delete("/matches/{match_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["matches"])
async def delete_match(
    match_id: str,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
) -> Response:
    """Permanently delete one of the user's matches."""
    await db.match.delete(match_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
