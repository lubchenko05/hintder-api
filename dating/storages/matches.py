"""Data access for ``Match`` rows (a user's match archive)."""

from typing import Any

import sqlalchemy as sa

from dating.models.match import Match
from dating.storages.base import BaseStorage
from dating.utils.error_handler import NotFoundException


class MatchStorage(BaseStorage):
    """List / fetch / upsert / delete matches, always scoped to one user."""

    async def list_for_user(self, user_id: str) -> list[Match]:
        """Return all of the user's matches, most-recently-updated first."""
        stmt = sa.select(Match).where(Match.user_id == user_id).order_by(Match.updated_at_ms.desc())
        async with self._session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_for_user(self, match_id: str, user_id: str) -> Match | None:
        """Return one match if it belongs to the user, else ``None``."""
        stmt = sa.select(Match).where(Match.id == match_id, Match.user_id == user_id)
        async with self._session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def upsert(self, match_id: str, user_id: str, data: dict[str, Any]) -> Match:
        """Insert the match or update it in place (scoped to the user)."""
        async with self._begin() as session:
            match = await session.scalar(
                sa.select(Match)
                .where(Match.id == match_id, Match.user_id == user_id)
                .with_for_update()
            )
            if match is None:
                match = Match(id=match_id, user_id=user_id, **data)
                session.add(match)
            else:
                for key, value in data.items():
                    setattr(match, key, value)
            await session.flush()
            await session.refresh(match)
            return match

    async def delete(self, match_id: str, user_id: str) -> None:
        """Permanently delete the user's match; 404 if it isn't theirs."""
        async with self._begin() as session:
            match = await session.scalar(
                sa.select(Match).where(Match.id == match_id, Match.user_id == user_id)
            )
            if match is None:
                raise NotFoundException(f"Match {match_id} not found")
            await session.delete(match)
