"""Process entry point — builds the FastAPI app and runs uvicorn in dev."""

import logging
import logging.config
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse, PlainTextResponse
from starlette.middleware.cors import CORSMiddleware

# Load local env overrides before anything reads config.
_env_file = Path(__file__).parent / "secrets" / "local.env"
if _env_file.exists():
    load_dotenv(_env_file)

from dating import routers  # noqa: E402
from dating.config import get_config  # noqa: E402
from dating.dependencies import on_shutdown, on_startup  # noqa: E402
from dating.utils.error_handler import setup_error_handlers  # noqa: E402

LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s-%(levelname)s-%(name)s::%(module)s:%(lineno)s:: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "": {"level": "INFO", "handlers": ["default"]},
        "uvicorn.access": {"level": "INFO", "handlers": ["default"], "propagate": False},
        "uvicorn.error": {"level": "INFO", "handlers": ["default"], "propagate": False},
    },
}
logging.config.dictConfig(LOG_CONFIG)


def add_middlewares(app: FastAPI) -> None:
    """Attach permissive CORS.

    Auth is a Bearer token in the Authorization header (no cookies), so we
    don't need credentialed CORS — which means we can use a wildcard origin.
    NOTE: ``allow_origins=["*"]`` and ``allow_credentials=True`` are mutually
    exclusive (browsers reject ``Access-Control-Allow-Origin: *`` with
    credentials), so credentials stay off.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    config = get_config()
    app = FastAPI(
        title="hintder API",
        description="hintder — dating wingman backend",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url=None if config.is_prod else "/api/openapi.json",
        default_response_class=ORJSONResponse,
    )

    app.include_router(routers.router)
    add_middlewares(app)
    setup_error_handlers(app)

    @app.get("/robots.txt", response_class=PlainTextResponse)
    async def robots_txt() -> str:
        """Disallow crawling of the API surface."""
        return "User-agent: *\nDisallow: /\n"

    @app.on_event("startup")
    async def app_startup() -> None:
        await on_startup(app)

    @app.on_event("shutdown")
    async def app_shutdown() -> None:
        await on_shutdown(app)

    return app


if __name__ == "__main__":
    cfg = get_config()
    uvicorn.run(
        "main:create_app",
        host=cfg.app_host,
        port=cfg.app_port,
        factory=True,
        reload=cfg.is_dev,
        reload_dirs=["dating"] if cfg.is_dev else None,
        log_config=LOG_CONFIG,
    )
