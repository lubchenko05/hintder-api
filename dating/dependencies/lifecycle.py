"""FastAPI lifespan hooks — wire/unwire the ``App`` container."""

from fastapi import FastAPI

from dating.app import App
from dating.config import get_config


async def on_startup(fastapi_app: FastAPI) -> None:
    """Construct the ``App`` container and stash it on ``app.state``."""
    app = App(cfg=get_config())
    await app.setup()
    fastapi_app.state.app = app


async def on_shutdown(fastapi_app: FastAPI) -> None:
    """Tear down the ``App`` container (closes the DB engine, HTTP clients)."""
    if hasattr(fastapi_app.state, "app"):
        await fastapi_app.state.app.close()
