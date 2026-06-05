"""Read/reply business logic — AI calls with backend-controlled hint spend.

Spending is server-authoritative: every Gemini-calling operation costs one hint
and the spend happens HERE (atomic ``db.hint.consume``), never on the client —
so a client can't get a free model call. Each op:
  1. fail-fast with 402 if the balance is already empty,
  2. call Gemini,
  3. spend one hint on success (don't charge for a failed generation).

Granting hints is also backend-only (see ``bl.billing`` / Paddle webhook).
"""

import logging

from dating.bl import hints as bl_hints
from dating.models.hint import (
    HINT_KIND_PROFILE_READ,
    HINT_KIND_REPLY_DRAFT,
)
from dating.models.user import User
from dating.services.ai import (
    AIClient,
    ConversationTurnInput,
    FollowUpAnalysisDTO,
    GeneratedMessageDTO,
    ProfileAnalysisDTO,
)
from dating.storages import DBStorage

logger = logging.getLogger(__name__)

# Hint kinds for the consumption ledger (free-form strings).
_KIND_OPENERS = "openers"
_KIND_TWEAK = "tweak"


async def analyze_profile(
    db: DBStorage, ai: AIClient, *, user: User, images: list[str], context: str | None
) -> ProfileAnalysisDTO:
    """Read profile screenshots into a structured analysis. Costs 1 hint."""
    mode = await bl_hints.precheck(db, user)
    result = await ai.analyze_profile(images=images, context=context)
    await bl_hints.commit(db, user, kind=HINT_KIND_PROFILE_READ, mode=mode)
    return result


async def generate_messages(
    db: DBStorage, ai: AIClient, *, user: User, analysis: ProfileAnalysisDTO, style: str, tone: str
) -> list[GeneratedMessageDTO]:
    """Draft five openers in the chosen voice. Costs 1 hint."""
    mode = await bl_hints.precheck(db, user)
    result = await ai.generate_messages(analysis=analysis, style=style, tone=tone)
    await bl_hints.commit(db, user, kind=_KIND_OPENERS, mode=mode)
    return result


async def analyze_reply(
    db: DBStorage,
    ai: AIClient,
    *,
    user: User,
    conversation: list[ConversationTurnInput],
    analysis: ProfileAnalysisDTO,
) -> FollowUpAnalysisDTO:
    """Read her latest reply and recommend the next move. Costs 1 hint."""
    mode = await bl_hints.precheck(db, user)
    result = await ai.analyze_reply(conversation=conversation, analysis=analysis)
    await bl_hints.commit(db, user, kind=HINT_KIND_REPLY_DRAFT, mode=mode)
    return result


async def regenerate_message(
    db: DBStorage, ai: AIClient, *, user: User, message_text: str, instruction: str, tone: str
) -> GeneratedMessageDTO:
    """Rewrite one message per a freeform instruction. Costs 1 hint."""
    mode = await bl_hints.precheck(db, user)
    result = await ai.regenerate_message(
        message_text=message_text, instruction=instruction, tone=tone
    )
    await bl_hints.commit(db, user, kind=_KIND_TWEAK, mode=mode)
    return result
