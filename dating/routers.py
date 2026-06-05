"""Top-level router aggregation. All API endpoints live under ``/api/v1``."""

from fastapi import APIRouter, Response

from dating.views.auth import router as auth_router
from dating.views.billing import router as billing_router
from dating.views.hints import router as hints_router
from dating.views.legal import router as legal_router
from dating.views.matches import router as matches_router
from dating.views.paddle_webhook import router as paddle_webhook_router
from dating.views.profile import router as profile_router
from dating.views.reads import router as reads_router

router_v1 = APIRouter(prefix="/v1")
router_v1.include_router(auth_router, tags=["auth"])
router_v1.include_router(profile_router, tags=["profile"])
router_v1.include_router(hints_router, tags=["hints"])
router_v1.include_router(reads_router, tags=["reads"])
router_v1.include_router(matches_router, tags=["matches"])
router_v1.include_router(billing_router, tags=["billing"])
router_v1.include_router(paddle_webhook_router, tags=["paddle"])
router_v1.include_router(legal_router, tags=["legal"])

router = APIRouter(prefix="/api")
router.include_router(router_v1)


@router.get("/health", include_in_schema=False)
async def health() -> Response:
    """Liveness probe — returns ``ok`` with no DB round-trip."""
    return Response("ok")
