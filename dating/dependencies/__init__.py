"""FastAPI dependency-injection helpers, re-exported for ergonomic imports.

- ``inj``       — service handles from ``app.inj`` (db, ai, paddle)
- ``auth``      — token decoding + current-user resolution
- ``lifecycle`` — ``on_startup`` / ``on_shutdown``
- ``pagination``— offset paginator + response envelope
"""

from dating.dependencies.auth import (
    get_current_user,
    get_current_user_id,
    get_optional_current_user_id,
    oauth2_scheme,
)
from dating.dependencies.inj import (
    get_ai_client,
    get_db_session,
    get_db_storage,
    get_paddle_service,
    get_storage_service,
)
from dating.dependencies.lifecycle import on_shutdown, on_startup
from dating.dependencies.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PaginatedResponse,
    Paginator,
)

__all__ = [
    "oauth2_scheme",
    "get_current_user_id",
    "get_optional_current_user_id",
    "get_current_user",
    "get_db_session",
    "get_db_storage",
    "get_ai_client",
    "get_paddle_service",
    "get_storage_service",
    "on_startup",
    "on_shutdown",
    "Paginator",
    "PaginatedResponse",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
]
