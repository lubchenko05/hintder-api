"""Cursor-free offset pagination helpers.

``Paginator`` is a ``Depends()``-able query-param bundle; ``PaginatedResponse``
is the generic envelope returned by list endpoints.
"""

from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

T = TypeVar("T")


class Paginator(BaseModel):
    """Bundle of ``limit``/``offset`` query params, clamped to sane bounds."""

    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT
    offset: Annotated[int, Query(ge=0)] = 0


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic list envelope: ``items`` plus the total row count."""

    items: list[T]
    total: int
    limit: int
    offset: int
