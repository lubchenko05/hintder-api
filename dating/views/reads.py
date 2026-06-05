"""AI generation endpoints — analyze a profile, draft openers, coach replies.

All require auth and are billed by the BACKEND: each spends one hint (atomic,
in ``bl.reads``) — the client never controls the spend. Responses are the
camelCase AI DTOs, consumed directly by the frontend.
"""

from uuid import uuid4

from fastapi import APIRouter, Depends

from dating.bl import reads as bl_reads
from dating.dependencies import (
    get_ai_client,
    get_current_user,
    get_db_storage,
    get_storage_service,
)
from dating.models.user import User
from dating.serializers.reads import (
    AnalyzeProfileValidator,
    AnalyzeReplyValidator,
    GenerateMessagesValidator,
    RegenerateMessageValidator,
    SignedUrlsValidator,
)
from dating.services.ai import (
    AIClient,
    FollowUpAnalysisDTO,
    GeneratedMessageDTO,
    ProfileAnalysisDTO,
)
from dating.services.storage import StorageService
from dating.storages import DBStorage

router = APIRouter()


@router.post("/reads/analyze", response_model=ProfileAnalysisDTO, tags=["reads"])
async def analyze_profile(
    payload: AnalyzeProfileValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
    ai: AIClient = Depends(get_ai_client),
    storage: StorageService = Depends(get_storage_service),
) -> ProfileAnalysisDTO:
    """Read profile screenshots into a structured analysis. Spends 1 hint.

    Screenshots are also stored (best-effort) for 30 days and their URIs
    returned on the result, so the match can be revisited.
    """
    result = await bl_reads.analyze_profile(
        db, ai, user=user, images=payload.images, context=payload.context
    )
    if payload.images:
        result.imageUrls = await storage.upload_read_images(
            user_id=user.id, read_id=uuid4().hex, images=payload.images
        )
    return result


@router.post("/reads/signed-urls", response_model=list[str], tags=["reads"])
async def signed_urls(
    payload: SignedUrlsValidator,
    user: User = Depends(get_current_user),
    storage: StorageService = Depends(get_storage_service),
) -> list[str]:
    """Exchange a saved match's ``gs://`` screenshot URIs for view URLs.

    The screenshots bucket is private, so a revisited match's photos can't be
    loaded directly. The client posts the stored URIs and gets short-lived
    signed GET URLs back. Costs no hint (no AI involved).
    """
    return await storage.signed_urls(user_id=user.id, uris=payload.uris)


@router.post("/reads/messages", response_model=list[GeneratedMessageDTO], tags=["reads"])
async def generate_messages(
    payload: GenerateMessagesValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
    ai: AIClient = Depends(get_ai_client),
) -> list[GeneratedMessageDTO]:
    """Draft five openers in the chosen voice. Spends 1 hint."""
    return await bl_reads.generate_messages(
        db, ai, user=user, analysis=payload.analysis, style=payload.style, tone=payload.tone
    )


@router.post("/reads/reply", response_model=FollowUpAnalysisDTO, tags=["reads"])
async def analyze_reply(
    payload: AnalyzeReplyValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
    ai: AIClient = Depends(get_ai_client),
) -> FollowUpAnalysisDTO:
    """Read her latest reply and recommend the next move. Spends 1 hint."""
    return await bl_reads.analyze_reply(
        db, ai, user=user, conversation=payload.conversation, analysis=payload.analysis
    )


@router.post("/reads/tweak", response_model=GeneratedMessageDTO, tags=["reads"])
async def regenerate_message(
    payload: RegenerateMessageValidator,
    user: User = Depends(get_current_user),
    db: DBStorage = Depends(get_db_storage),
    ai: AIClient = Depends(get_ai_client),
) -> GeneratedMessageDTO:
    """Rewrite one message per a freeform instruction. Spends 1 hint."""
    return await bl_reads.regenerate_message(
        db,
        ai,
        user=user,
        message_text=payload.message_text,
        instruction=payload.instruction,
        tone=payload.tone,
    )
