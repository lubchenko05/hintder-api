"""Application configuration.

Values resolve with priority: explicit kwargs → environment variables → GCP
Secret Manager (prod only) → field defaults. ``get_config()`` returns a cached
singleton; tests can clear it via ``_reset_config_cache``.
"""

import os
from enum import Enum
from typing import Any
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from dating.utils.secret_manager import access_secret_version

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Env(str, Enum):
    """Deployment environment selector."""

    DEV = "dev"
    TEST = "test"
    PROD = "prod"
    PYTEST = "pytest"


class Config(BaseSettings):
    """Environment-driven settings for the hintder API."""

    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    env: Env = Env.DEV
    app_host: str = "0.0.0.0"
    app_port: int = 8010

    secret_key: str = "dummy_secret_key_for_dev"
    jwt_secret_key: str = "dummy_jwt_secret_for_dev"

    # Public URLs. Prod: https://hintder.app + https://api.hintder.app
    frontend_base_url: str = "http://localhost:3000"
    backend_base_url: str = "http://localhost:8010"

    # Database — local dev defaults match the role the user provisions by hand.
    postgres_db: str = "dating"
    postgres_host: str = "localhost"
    postgres_password: str = "dating"
    postgres_port: int = 5432
    postgres_user: str = "dating"

    # Connection pool (per OS process). Single API service, modest pool.
    db_pool_size: int = 5
    db_max_overflow: int = 5

    # Firebase Admin — service-account JSON path. When empty, the Admin SDK
    # falls back to Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS).
    # Firebase Admin — its OWN service account (separate from the GCP SA below),
    # used only to verify frontend ID tokens.
    firebase_credentials_file: str = "secrets/hintder-ai-firebase.json"
    firebase_project_id: str = "hintder-ai"

    # GCP (prod secret resolution / Cloud Run)
    google_cloud_project: str = ""

    # Cloud Storage for uploaded screenshots — a dedicated GCS bucket + its own
    # service account (decoupled from Firebase). Objects are kept
    # ``storage_retention_days`` then auto-deleted via a bucket lifecycle rule
    # (see scripts/set_storage_lifecycle.py). Empty bucket = storage disabled.
    # When ``storage_credentials_file`` is blank, Application Default Creds are
    # used (e.g. the Cloud Run runtime SA).
    storage_bucket: str = "dating-client-storage-30d"
    storage_credentials_file: str = "secrets/hintder-ai-sa.json"
    storage_prefix: str = "reads"
    storage_retention_days: int = 30

    # Free starter hints granted once per new user.
    free_hints_grant: int = 3

    # Subscription economics.
    # Rollover cap on accumulated SUBSCRIPTION hints = this many monthly cycles
    # of the plan's allotment (top-ups are never capped).
    rollover_cap_cycles: int = 3
    # Ultimate (unlimited) soft fair-use limit — reads allowed per UTC day.
    fair_use_daily_limit: int = 200

    # AI processing — real Gemini, no mocks. Two auth modes:
    #   • Vertex AI (default) — hintder-ai GCP project + the shared GCP SA
    #   • Google AI Studio API key (set ``ai_api_key`` + ``ai_use_vertex=False``)
    ai_model: str = "gemini-3.5-flash"  # latest Flash (not Pro)
    ai_use_vertex: bool = True
    ai_vertex_project: str = "hintder-ai"
    ai_vertex_location: str = "global"  # Gemini 3.x are served on the global endpoint
    ai_vertex_credentials_file: str = "secrets/hintder-ai-sa.json"
    ai_api_key: str = ""

    # Paddle Billing — mocked until real IDs exist. ``paddle_enabled`` stays
    # False while the API key is blank, which keeps the checkout flow on the
    # local mock path.
    paddle_api_key: str = ""
    paddle_webhook_secret: str = ""
    paddle_environment: str = "sandbox"  # "sandbox" | "production"

    # Paddle commercial terms surfaced to the client + legal pages.
    # Paddle (Merchant of Record) requires a refund window be stated; ours is
    # 14 days. Keep this in sync with every "refund within N days" string.
    refund_window_days: int = 14

    @model_validator(mode="before")
    @classmethod
    def load_from_env_and_secret_manager(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Overlay env vars, then GCP Secret Manager, onto unset fields."""
        secrets_to_load = [
            "secret_key",
            "jwt_secret_key",
            "frontend_base_url",
            "backend_base_url",
            "postgres_db",
            "postgres_host",
            "postgres_password",
            "postgres_port",
            "postgres_user",
            "firebase_credentials_file",
            "firebase_project_id",
            "google_cloud_project",
            "storage_bucket",
            "storage_credentials_file",
            "ai_model",
            "ai_vertex_project",
            "ai_vertex_location",
            "ai_vertex_credentials_file",
            "ai_api_key",
            "paddle_api_key",
            "paddle_webhook_secret",
            "paddle_environment",
        ]
        for secret_name in secrets_to_load:
            if data.get(secret_name) is not None and secret_name in data:
                continue
            env_value = os.environ.get(secret_name.upper())
            if env_value is not None:
                data[secret_name] = env_value
                continue
            secret_value = access_secret_version(secret_name.upper())
            if secret_value is not None:
                data[secret_name] = secret_value

        # Empty-string env vars for typed fields → drop so defaults apply.
        for field in ("postgres_port", "app_port", "db_pool_size", "db_max_overflow"):
            if data.get(field) == "":
                del data[field]
        return data

    @property
    def gcp_project(self) -> str:
        """Alias for ``google_cloud_project``."""
        return self.google_cloud_project

    @property
    def paddle_enabled(self) -> bool:
        """True once a real Paddle API key is configured."""
        return bool(self.paddle_api_key)

    def get_db_url(self, driver: str) -> str:
        """Build a SQLAlchemy URL for the given driver (``asyncpg``/``psycopg2``)."""
        encoded_password = quote_plus(self.postgres_password)
        return (
            f"postgresql+{driver}://{self.postgres_user}:{encoded_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def db_url(self) -> str:
        """Async (asyncpg) database URL."""
        return self.get_db_url(driver="asyncpg")

    @property
    def db_url_sync(self) -> str:
        """Sync (psycopg2) database URL — used by Alembic offline mode."""
        return self.get_db_url(driver="psycopg2")

    @property
    def is_dev(self) -> bool:
        """True in the local development environment."""
        return self.env == Env.DEV

    @property
    def is_test(self) -> bool:
        """True in the TEST environment."""
        return self.env == Env.TEST

    @property
    def is_prod(self) -> bool:
        """True in production."""
        return self.env == Env.PROD

    @property
    def is_pytest(self) -> bool:
        """True under the pytest runner."""
        return self.env == Env.PYTEST


_config: Config | None = None


def get_config() -> Config:
    """Return the cached config singleton, constructing it on first call."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def _reset_config_cache() -> None:
    """Test-only: clear the cached singleton so the next read re-evaluates env."""
    global _config
    _config = None
