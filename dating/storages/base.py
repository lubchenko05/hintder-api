"""Base class for all storage repositories.

Every concrete storage extends ``BaseStorage`` and gains:
- ``self._session`` — the async sessionmaker
- ``self._begin()`` — short-cut for the common transactional block

Conventions (enforced by review, not mypy):
- Public methods return ORM instances, never raw ``dict``.
- ``get_*`` methods that can miss return ``Model | None``; each has a paired
  ``get_*_or_error`` sibling that raises ``NotFoundException``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from dating.types import sessionmaker


class BaseStorage:
    """Holds the async sessionmaker and a transactional-session helper."""

    def __init__(self, db_session: sessionmaker) -> None:
        """Store the sessionmaker used to open per-operation sessions."""
        self._session = db_session

    @asynccontextmanager
    async def _begin(self) -> AsyncIterator[AsyncSession]:
        """Yield a session already inside a transaction (auto-commit on exit)."""
        async with self._session() as session, session.begin():
            yield session
