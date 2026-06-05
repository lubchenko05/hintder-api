"""Application container with a tiny dependency-injection registry.

``App.setup()`` initialises shared resources (DB engine, sessionmaker, storage
aggregate, services) into ``inj``; ``App.close()`` disposes them. The same
instance backs the FastAPI process and any future scripts/tasks.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine

from dating.config import Config
from dating.storages import DBStorage
from dating.types import sessionmaker

logger = logging.getLogger(__name__)


class Inj:
    """Minimal string-keyed dependency-injection container."""

    def __init__(self) -> None:
        """Start with an empty provider map."""
        self._provides: dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        """Return the provider registered under ``key`` (raises ``KeyError`` if absent)."""
        return self._provides[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Register ``value`` under ``key``."""
        self._provides[key] = value

    def __contains__(self, key: str) -> bool:
        """Return whether ``key`` has a registered provider."""
        return key in self._provides

    def get(self, key: str, default: Any = None) -> Any:
        """Return the provider for ``key`` or ``default`` if unset."""
        return self._provides.get(key, default)


class App:
    """Owns the lifecycle of every shared dependency in the process."""

    def __init__(
        self,
        cfg: Config,
        *,
        db_pool_size: int | None = None,
        db_max_overflow: int | None = None,
    ) -> None:
        """Capture config and optional pool overrides; resources init in ``setup``."""
        self.cfg = cfg
        self.inj = Inj()
        self._db_pool_size = db_pool_size if db_pool_size is not None else cfg.db_pool_size
        self._db_max_overflow = (
            db_max_overflow if db_max_overflow is not None else cfg.db_max_overflow
        )

    async def setup(self) -> None:
        """Initialise all application dependencies into ``inj``."""
        logger.info("Setting up application dependencies...")

        engine = create_async_engine(
            self.cfg.db_url,
            connect_args={
                "timeout": 10,
                "command_timeout": 20,
                "server_settings": {
                    "application_name": "hintder",
                    "statement_timeout": "30000",
                    "idle_in_transaction_session_timeout": "60000",
                },
            },
            pool_size=self._db_pool_size,
            max_overflow=self._db_max_overflow,
            pool_timeout=10,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        self.inj["db_engine"] = engine
        self.inj["db_session"] = db_session = sessionmaker(engine, expire_on_commit=False)
        self.inj["db"] = DBStorage(db_session=db_session)

        self._setup_services()

        logger.info("Application dependencies ready.")

    def _setup_services(self) -> None:
        """Wire external-integration services (AI, Paddle) into ``inj``.

        Kept separate from DB setup so the service wiring can grow per feature
        phase without disturbing the data layer.
        """
        from dating.services.ai import build_ai_client
        from dating.services.paddle import PaddleService
        from dating.services.storage import StorageService

        self.inj["ai"] = build_ai_client(self.cfg)
        self.inj["paddle"] = PaddleService(self.cfg)
        self.inj["storage"] = StorageService(self.cfg)

    async def close(self) -> None:
        """Dispose the DB engine and any other closable resources."""
        logger.info("Closing application dependencies...")
        engine = self.inj.get("db_engine")
        if engine is not None:
            await engine.dispose()
