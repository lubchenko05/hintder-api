"""Service-injection dependencies — the single source for ``app.inj`` lookups.

Views import these instead of reaching into ``request.app.state.app.inj``
directly, so signatures stay stable when an implementation swaps (e.g. the AI
client going from mock to real).
"""

from typing import Any, TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from dating.services.ai import AIClient
    from dating.services.email import EmailService
    from dating.services.paddle import PaddleService
    from dating.services.storage import StorageService
    from dating.storages import DBStorage
    from dating.types import sessionmaker


def _inj(request: Request, key: str) -> Any:
    """Look up ``key`` in the application's injection container."""
    return request.app.state.app.inj[key]


def get_db_session(request: Request) -> "sessionmaker":
    """Return the shared async sessionmaker."""
    return _inj(request, "db_session")


def get_db_storage(request: Request) -> "DBStorage":
    """Return the aggregate ``DBStorage``."""
    return _inj(request, "db")


def get_ai_client(request: Request) -> "AIClient":
    """Return the opener-generation client (mock or real)."""
    return _inj(request, "ai")


def get_paddle_service(request: Request) -> "PaddleService":
    """Return the Paddle billing service (mock or real)."""
    return _inj(request, "paddle")


def get_storage_service(request: Request) -> "StorageService":
    """Return the screenshot storage service."""
    return _inj(request, "storage")


def get_email_service(request: Request) -> "EmailService":
    """Return the transactional email service (Brevo)."""
    return _inj(request, "email")
