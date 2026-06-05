"""Paddle webhook endpoint — raw-body signature verification + processing."""

from fastapi import APIRouter, Depends, Request, Response

from dating.bl import paddle_webhook as bl_webhook
from dating.dependencies import get_db_storage, get_paddle_service
from dating.services.paddle import PaddleService
from dating.storages import DBStorage

router = APIRouter()


@router.post("/paddle/webhook", include_in_schema=False, tags=["paddle"])
async def paddle_webhook(
    request: Request,
    db: DBStorage = Depends(get_db_storage),
    paddle: PaddleService = Depends(get_paddle_service),
) -> Response:
    """Receive a Paddle webhook. Signature is verified over the raw bytes."""
    raw_body = await request.body()
    signature = request.headers.get("Paddle-Signature", "")
    await bl_webhook.handle_webhook(db, paddle, raw_body=raw_body, signature_header=signature)
    return Response("ok")
