"""Shared type aliases used across layers."""

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

if TYPE_CHECKING:
    sessionmaker = async_sessionmaker[AsyncSession]
else:
    sessionmaker = async_sessionmaker

UserID = str
"""Firebase UID, also the primary key of ``users``."""
