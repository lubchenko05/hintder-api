"""Declarative base + shared column type aliases for all ORM models."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import declarative_base

metadata = sa.MetaData()


class BaseModel:
    """Mixin giving every model a readable ``repr`` driven by ``__repr_attrs__``."""

    __repr_attrs__: list[str] = []

    def __repr__(self) -> str:
        """Render ``<ClassName attr=value ...>`` for the declared repr attrs."""
        name = self.__class__.__name__
        params = " ".join(
            f"{attr}={getattr(self, attr)}" for attr in self.__repr_attrs__ if hasattr(self, attr)
        )
        return f"<{name} {params}>"


Base: Any = declarative_base(metadata=metadata, cls=BaseModel)
