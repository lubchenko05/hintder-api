"""Request validators for the AI generation endpoints.

Responses are the AI DTOs themselves (``ProfileAnalysisDTO`` etc.) — camelCase,
drop-in for the frontend. Requests reuse those DTOs where they carry an analysis
back (the client round-trips the analysis it received).
"""

from dating.serializers.base import BaseValidator
from dating.services.ai import ConversationTurnInput, ProfileAnalysisDTO
from dating.validators import LongText, NonEmptyStr


class AnalyzeProfileValidator(BaseValidator):
    """``POST /reads/analyze`` — base64 screenshots (+ optional typed context)."""

    images: list[str] = []
    context: LongText | None = None


class SignedUrlsValidator(BaseValidator):
    """``POST /reads/signed-urls`` — stored ``gs://`` URIs to view-sign."""

    uris: list[str] = []


class GenerateMessagesValidator(BaseValidator):
    """``POST /reads/messages`` — analysis + chosen voice/risk."""

    analysis: ProfileAnalysisDTO
    style: str = "confident"
    tone: str = "natural"


class AnalyzeReplyValidator(BaseValidator):
    """``POST /reads/reply`` — the thread so far + the profile analysis."""

    conversation: list[ConversationTurnInput]
    analysis: ProfileAnalysisDTO


class RegenerateMessageValidator(BaseValidator):
    """``POST /reads/tweak`` — one message + a freeform rewrite instruction."""

    message_text: NonEmptyStr
    instruction: NonEmptyStr
    tone: str = "confident"


class DecodeMessageValidator(BaseValidator):
    """``POST /reads/decode`` — one message from her (+ optional profile read)."""

    her_message: NonEmptyStr
    analysis: ProfileAnalysisDTO | None = None


class OptimizeProfileValidator(BaseValidator):
    """``POST /reads/optimize`` — the USER's own profile screenshots + bio."""

    images: list[str] = []
    bio: LongText | None = None
