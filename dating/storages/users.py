"""Data access for ``User`` rows."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from dating.models.user import User
from dating.storages.base import BaseStorage
from dating.utils.datetime import utcnow
from dating.utils.error_handler import NotFoundException


class UserStorage(BaseStorage):
    """Read/write operations for the ``users`` table."""

    async def get_by_id(self, user_id: str) -> User | None:
        """Return the user with this id, or ``None``."""
        async with self._session() as session:
            return await session.get(User, user_id)

    async def get_by_id_or_error(self, user_id: str) -> User:
        """Return the user with this id, or raise ``NotFoundException``."""
        user = await self.get_by_id(user_id)
        if user is None:
            raise NotFoundException(f"User {user_id} not found")
        return user

    async def get_by_email(self, email: str) -> User | None:
        """Return the user with this email, or ``None``."""
        stmt = sa.select(User).where(User.email == email)
        async with self._session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def device_has_grant(self, device_id: str) -> bool:
        """True if any account was already created on this device (claimed the grant)."""
        stmt = sa.select(sa.exists().where(User.device_id == device_id))
        async with self._session() as session:
            result = await session.execute(stmt)
            return bool(result.scalar())

    async def get_or_create(
        self,
        user_id: str,
        *,
        email: str | None = None,
        name: str | None = None,
        avatar: str | None = None,
        free_hints: int = 3,
        device_id: str | None = None,
    ) -> tuple[User, bool]:
        """Insert this user if absent. Returns the row and whether WE inserted it.

        A browser routinely has several ``/auth/firebase`` calls in flight at
        once — a retry, a second tab, a re-fired auth listener. Each one reads
        "no such user" before any of them inserts, so a plain INSERT left the
        losers raising IntegrityError and the endpoint answering 500. Because a
        500 escapes before the CORS middleware runs, the browser reported it as
        a CORS failure, which hid the real cause for a long time.

        ON CONFLICT DO NOTHING lets a losing racer fall through and read the
        winner's row instead. The flag matters to the caller: only the request
        that actually inserted may announce a registration, or one sign-up
        would alert the operator and bill Meta several times over.
        """
        now = utcnow()
        stmt = (
            pg_insert(User)
            .values(
                id=user_id,
                email=email,
                name=name,
                avatar=avatar,
                free_hints=free_hints,
                sub_hints=0,
                paid_hints=0,
                device_id=device_id,
                created_at=now,
                updated_at=now,
            )
            # Scoped to the primary key: a clash on the unique email column is a
            # different situation (same person, a second Firebase identity) and
            # must not be silently swallowed here.
            .on_conflict_do_nothing(index_elements=[User.id])
            .returning(User.id)
        )
        async with self._begin() as session:
            result = await session.execute(stmt)
            inserted = result.scalar_one_or_none() is not None

        user = await self.get_by_id(user_id)
        if user is None:
            raise NotFoundException(f"User {user_id} vanished between upsert and read")
        return user, inserted

    async def update(self, user_id: str, data: dict[str, Any]) -> User | None:
        """Apply ``data`` (column→value), bump ``updated_at``; ``None`` if missing."""
        async with self._begin() as session:
            user = await session.get(User, user_id)
            if user is None:
                return None
            for key, value in data.items():
                setattr(user, key, value)
            user.updated_at = utcnow()
            await session.flush()
            await session.refresh(user)
            return user

    async def update_or_error(self, user_id: str, data: dict[str, Any]) -> User:
        """Like :meth:`update` but raises ``NotFoundException`` if missing."""
        user = await self.update(user_id, data)
        if user is None:
            raise NotFoundException(f"User {user_id} not found")
        return user
