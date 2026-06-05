"""Typed application exceptions + FastAPI handlers.

Every domain error raised inside ``bl``/``storages`` is an ``AppException``
subclass with a fixed ``status_code``. The handlers registered by
``setup_error_handlers`` translate those (and Pydantic ``ValidationError``)
into a consistent JSON shape: ``{"detail": ...}``.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base typed exception. Subclasses fix ``status_code`` as a class attribute."""

    status_code: int = 500

    def __init__(self, detail: str = "Internal error") -> None:
        """Store ``detail`` for the JSON response body."""
        super().__init__(detail)
        self.detail = detail


class NotFoundException(AppException):
    """Requested resource does not exist (HTTP 404)."""

    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, detail: str = "Resource not found") -> None:
        """Default message: ``Resource not found``."""
        super().__init__(detail)


class ForbiddenException(AppException):
    """Caller is authenticated but not allowed (HTTP 403)."""

    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, detail: str = "Access forbidden") -> None:
        """Default message: ``Access forbidden``."""
        super().__init__(detail)


class BadRequestException(AppException):
    """Malformed or semantically invalid request (HTTP 400)."""

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail: str = "Bad request") -> None:
        """Default message: ``Bad request``."""
        super().__init__(detail)


class UnauthorizedException(AppException):
    """Missing or invalid credentials (HTTP 401)."""

    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self, detail: str = "Unauthorized") -> None:
        """Default message: ``Unauthorized``."""
        super().__init__(detail)


class ConflictException(AppException):
    """State conflict — e.g. duplicate idempotency key (HTTP 409)."""

    status_code = status.HTTP_409_CONFLICT

    def __init__(self, detail: str = "Conflict") -> None:
        """Default message: ``Conflict``."""
        super().__init__(detail)


class PaymentRequiredException(AppException):
    """Caller is out of hints and must buy more (HTTP 402)."""

    status_code = status.HTTP_402_PAYMENT_REQUIRED

    def __init__(self, detail: str = "Out of hints") -> None:
        """Default message: ``Out of hints``."""
        super().__init__(detail)


class TooManyRequestsException(AppException):
    """Caller hit a rate / fair-use limit (HTTP 429)."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, detail: str = "Daily limit reached") -> None:
        """Default message: ``Daily limit reached``."""
        super().__init__(detail)


class ServiceUnavailableException(AppException):
    """A downstream dependency is unavailable (HTTP 503)."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self, detail: str = "Service unavailable") -> None:
        """Default message: ``Service unavailable``."""
        super().__init__(detail)


class BadGatewayException(AppException):
    """A downstream dependency returned an invalid response (HTTP 502)."""

    status_code = status.HTTP_502_BAD_GATEWAY

    def __init__(self, detail: str = "Bad gateway") -> None:
        """Default message: ``Bad gateway``."""
        super().__init__(detail)


def setup_error_handlers(app: FastAPI) -> None:
    """Register exception handlers that emit a uniform ``{"detail": ...}`` body."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """Map an ``AppException`` to its declared status code."""
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
        """Surface Pydantic validation failures as HTTP 422."""
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all — log the traceback and return an opaque HTTP 500."""
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )
