"""Opener / reply generation — real Gemini, no mocks.

The product's core: given screenshots of a match's profile (or a chat thread)
plus a chosen tone, produce a rich, structured read and opener/reply candidates.

``AIClient`` is the protocol; ``GeminiAIClient`` is the real implementation
(Gemini 2.5 Flash — vision + JSON structured output). The DTOs returned here are
camelCase on purpose: they are the exact shapes the Next.js frontend consumes,
so responses are drop-in. The blocking google-genai SDK is wrapped in
``asyncio.to_thread`` so it never stalls the event loop.
"""

import asyncio
import base64
import logging
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel

from dating.config import Config
from dating.utils.error_handler import BadGatewayException

logger = logging.getLogger(__name__)

SUPPORTED_TONES = ("funny", "confident", "calm", "flirty", "smart", "short", "less-cringe")
DEFAULT_TONE = "confident"
# Risk dial levels (mirror the frontend ``MessageTone`` union).
RISK_LEVELS = ("safer", "natural", "bolder")

# Stable palettes for photo cards (server-injected — not the model's job).
_PALETTES = [
    ("#FE3C72", "#FF8552"),
    ("#7C5CFF", "#5BE3A9"),
    ("#FF6B6B", "#FFD93D"),
    ("#4D9DE0", "#7C5CFF"),
]


def normalise_tone(tone: str | None) -> str:
    """Coerce an arbitrary tone to a supported one (fallback to default)."""
    return tone if tone in SUPPORTED_TONES else DEFAULT_TONE


# ── Output DTOs (camelCase — mirror the frontend ``@/types``) ─────────────


class ProfileHookDTO(BaseModel):
    """A specific thing in her profile worth opening on + why."""

    topic: str
    why: str


class DateAngleDTO(BaseModel):
    """A 1-3 word date concept tuned to her profile."""

    title: str
    why: str


class PhotoSnapshotDTO(BaseModel):
    """A per-photo read; ``g1``/``g2``/``art`` are server-injected card visuals."""

    caption: str
    vibe: str
    tags: list[str]
    unlocks: str
    g1: str = "#FE3C72"
    g2: str = "#FF8552"
    art: int = 0


class PreviewOpenerDTO(BaseModel):
    """A free, ready-to-send opener for one voice × risk combination."""

    voice: str
    risk: str
    text: str


class ProfileAnalysisDTO(BaseModel):
    """The full structured read of a profile."""

    name: str
    age: int
    vibe: str
    hooks: list[ProfileHookDTO]
    avoid: list[str]
    angle: str  # humor | curiosity | calm | flirty
    interests: list[str]
    photoContext: list[PhotoSnapshotDTO]
    cosmicRead: str | None = None
    dateAngles: list[DateAngleDTO] | None = None
    timingWindow: str | None = None
    greenLightTopics: list[str] | None = None
    # One free opener per voice × risk (the StylePicker preview matrix).
    previews: list[PreviewOpenerDTO] | None = None
    # Stored screenshot URIs (gs://…), attached by the view after upload.
    imageUrls: list[str] | None = None


class GeneratedMessageDTO(BaseModel):
    """One opener/reply candidate. ``id`` is server-generated."""

    id: str
    text: str
    category: str  # best | safe | funny | flirty | short | risky
    label: str
    cringeRisk: int
    tone: str


class FollowUpAnalysisDTO(BaseModel):
    """The read of her latest reply + recommended next moves."""

    interestLevel: str  # high | medium | low | unclear
    tone: str
    shouldPush: bool
    suggestion: str
    nextMessages: list[GeneratedMessageDTO]
    doNotSend: str
    dateReadiness: int
    dateReadinessNote: str
    dateRecommendations: list[DateAngleDTO] | None = None
    dateInvites: list[GeneratedMessageDTO] | None = None
    urgencyWarning: str | None = None


class ConversationTurnInput(BaseModel):
    """One turn of the chat thread the user is coaching through."""

    role: str  # "me" | "her"
    text: str


# ── Gemini schema models (what the model fills — no server-only fields) ───


class _GeminiPhoto(BaseModel):
    caption: str
    vibe: str
    tags: list[str]
    unlocks: str


class _GeminiAnalysis(BaseModel):
    name: str
    age: int
    vibe: str
    hooks: list[ProfileHookDTO]
    avoid: list[str]
    angle: str
    interests: list[str]
    photoContext: list[_GeminiPhoto]
    cosmicRead: str
    dateAngles: list[DateAngleDTO]
    timingWindow: str
    greenLightTopics: list[str]
    previews: list[PreviewOpenerDTO]


class _GeminiMessage(BaseModel):
    text: str
    category: str
    label: str
    cringeRisk: int


class _GeminiMessageList(BaseModel):
    messages: list[_GeminiMessage]


class _GeminiFollowUp(BaseModel):
    interestLevel: str
    tone: str
    shouldPush: bool
    suggestion: str
    nextMessages: list[_GeminiMessage]
    doNotSend: str
    dateReadiness: int
    dateReadinessNote: str
    dateRecommendations: list[DateAngleDTO]
    dateInvites: list[_GeminiMessage]
    urgencyWarning: str


# ── Protocol ──────────────────────────────────────────────────────────────


class AIClient(Protocol):
    """Contract for the four generation operations the app needs."""

    async def analyze_profile(
        self, *, images: list[str], context: str | None
    ) -> ProfileAnalysisDTO:
        """Read profile screenshots (+ optional context) into a structured analysis."""
        ...

    async def generate_messages(
        self, *, analysis: ProfileAnalysisDTO, style: str, tone: str
    ) -> list[GeneratedMessageDTO]:
        """Draft five openers in the chosen style/tone for an analysed profile."""
        ...

    async def analyze_reply(
        self, *, conversation: list[ConversationTurnInput], analysis: ProfileAnalysisDTO
    ) -> FollowUpAnalysisDTO:
        """Read her latest reply and recommend the next move."""
        ...

    async def regenerate_message(
        self, *, message_text: str, instruction: str, tone: str
    ) -> GeneratedMessageDTO:
        """Rewrite one message per a freeform instruction."""
        ...


# ── Helpers ────────────────────────────────────────────────────────────────


def _decode_image(data: str) -> tuple[bytes, str]:
    """Split a data-URL or raw base64 string into (bytes, mime_type)."""
    mime = "image/jpeg"
    payload = data
    if data.startswith("data:"):
        header, _, payload = data.partition(",")
        if ";" in header and ":" in header:
            mime = header.split(":", 1)[1].split(";", 1)[0] or mime
    return base64.b64decode(payload), mime


def _msg(m: "_GeminiMessage", tone: str) -> GeneratedMessageDTO:
    """Promote a model message into the output DTO (id + tone added)."""
    return GeneratedMessageDTO(
        id=uuid4().hex[:10],
        text=m.text,
        category=m.category,
        label=m.label,
        cringeRisk=max(0, min(100, m.cringeRisk)),
        tone=tone,
    )


def _photos(photos: list["_GeminiPhoto"]) -> list[PhotoSnapshotDTO]:
    """Attach a rotating card palette to each photo read."""
    out: list[PhotoSnapshotDTO] = []
    for i, p in enumerate(photos):
        g1, g2 = _PALETTES[i % len(_PALETTES)]
        out.append(
            PhotoSnapshotDTO(
                caption=p.caption,
                vibe=p.vibe,
                tags=p.tags,
                unlocks=p.unlocks,
                g1=g1,
                g2=g2,
                art=i % 4,
            )
        )
    return out


_VOICE = (
    "You are hintder, an elite dating wingman. You write like a confident, funny "
    "version of the user — never like an AI. No em-dash pile-ups, no 'as an "
    "opener', no perfect-grammar stiffness. Lines are specific to her profile, "
    "create light tension, and hand her a clear way to reply. Keep it real, never "
    "cringe, never pick-up-artist."
)


class GeminiAIClient:
    """Real generation via Gemini 2.5 Flash (vision + JSON structured output).

    Authenticates either through Vertex AI (a GCP project + service account —
    the Seeto setup) or a Google AI Studio API key, chosen by ``cfg``.
    """

    def __init__(self, cfg: Config) -> None:
        """Construct the google-genai client (imports are lazy/local)."""
        import os

        from google import genai

        self._model = cfg.ai_model
        if cfg.ai_use_vertex:
            credentials = None
            if cfg.ai_vertex_credentials_file and os.path.exists(cfg.ai_vertex_credentials_file):
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_file(
                    cfg.ai_vertex_credentials_file,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            self._client = genai.Client(
                vertexai=True,
                project=cfg.ai_vertex_project,
                location=cfg.ai_vertex_location,
                credentials=credentials,
            )
        else:
            self._client = genai.Client(api_key=cfg.ai_api_key)

    async def _generate(self, *, contents: object, schema: type[BaseModel]) -> BaseModel:
        """Run one structured generate_content call off the event loop."""
        from google.genai import types

        def _call() -> BaseModel:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=contents,  # type: ignore[arg-type]
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.95,
                    system_instruction=_VOICE,
                ),
            )
            parsed = resp.parsed
            if not isinstance(parsed, BaseModel):
                raise BadGatewayException("Gemini returned no parseable result")
            return parsed

        try:
            return await asyncio.to_thread(_call)
        except BadGatewayException:
            raise
        except Exception as exc:
            logger.exception("Gemini call failed")
            raise BadGatewayException("AI generation failed") from exc

    async def analyze_profile(
        self, *, images: list[str], context: str | None
    ) -> ProfileAnalysisDTO:
        """See :class:`AIClient`."""
        from google.genai import types

        parts: list[object] = []
        for data in images[:6]:
            raw, mime = _decode_image(data)
            parts.append(types.Part.from_bytes(data=raw, mime_type=mime))
        voices = ", ".join(SUPPORTED_TONES)
        risks = ", ".join(RISK_LEVELS)
        parts.append(
            "Analyze this dating profile (screenshots above"
            + (f", plus context: {context}" if context else "")
            + "). Infer her name (use the visible one or a tasteful placeholder), "
            "age, vibe, the best hooks to open on, what to avoid, the strongest "
            "opening angle (humor|curiosity|calm|flirty), interests, a per-photo "
            "read, a short playful 'cosmic read', 2-3 date angles, a likely "
            "responsive timing window, and green-light topics.\n\n"
            f"Also fill `previews`: for EACH voice ({voices}) AND EACH risk "
            f"({risks}) — one ready-to-send opening line tailored to THIS profile "
            "(so one entry per voice×risk combination). Each entry is "
            "{voice, risk, text}. These are the free preview openers."
        )
        result = await self._generate(contents=parts, schema=_GeminiAnalysis)
        assert isinstance(result, _GeminiAnalysis)
        return ProfileAnalysisDTO(
            name=result.name,
            age=result.age,
            vibe=result.vibe,
            hooks=result.hooks,
            avoid=result.avoid,
            angle=result.angle,
            interests=result.interests,
            photoContext=_photos(result.photoContext),
            cosmicRead=result.cosmicRead,
            dateAngles=result.dateAngles,
            timingWindow=result.timingWindow,
            greenLightTopics=result.greenLightTopics,
            previews=result.previews,
        )

    async def generate_messages(
        self, *, analysis: ProfileAnalysisDTO, style: str, tone: str
    ) -> list[GeneratedMessageDTO]:
        """See :class:`AIClient`."""
        prompt = (
            f"Her profile read: {analysis.model_dump_json()}\n\n"
            f"Write 5 distinct opening messages in a '{style}' voice "
            f"(risk dial: {tone}). For each: the text, a category "
            "(best|safe|funny|flirty|short|risky), a 1-3 word label, and a "
            "cringeRisk 0-100 (lower is safer)."
        )
        result = await self._generate(contents=prompt, schema=_GeminiMessageList)
        assert isinstance(result, _GeminiMessageList)
        return [_msg(m, style) for m in result.messages]

    async def analyze_reply(
        self, *, conversation: list[ConversationTurnInput], analysis: ProfileAnalysisDTO
    ) -> FollowUpAnalysisDTO:
        """See :class:`AIClient`."""
        thread = "\n".join(f"{t.role}: {t.text}" for t in conversation)
        her_replies = sum(1 for t in conversation if t.role == "her")
        prompt = (
            f"Her profile read: {analysis.model_dump_json()}\n\n"
            f"The conversation so far:\n{thread}\n\n"
            f"She has replied {her_replies} time(s) so far. "
            "Read her latest reply. Return her interest level "
            "(high|medium|low|unclear), her tone, whether to push, a one-line "
            "suggestion, 3 next-message candidates, one thing to NOT send, and a "
            "dateReadiness 0-100 with a short note.\n"
            "Judge it from the actual dialogue — but lean towards NOT rushing: "
            "readiness should generally build over the back-and-forth rather than "
            "spike to 'ready to ask out' on a single warm reply. This is a soft "
            "recommendation, not a hard rule — if she's genuinely pushing to meet, "
            "trust that and move faster.\n"
            "Include date recommendations once it's warming. Only when readiness is "
            "genuinely high — AT LEAST 3-4 distinct ready-to-send date invites "
            "(vary the vibe/venue/timing for real choice) plus a short urgency "
            "warning (else leave those empty)."
        )
        result = await self._generate(contents=prompt, schema=_GeminiFollowUp)
        assert isinstance(result, _GeminiFollowUp)
        style = analysis.angle
        return FollowUpAnalysisDTO(
            interestLevel=result.interestLevel,
            tone=result.tone,
            shouldPush=result.shouldPush,
            suggestion=result.suggestion,
            nextMessages=[_msg(m, style) for m in result.nextMessages],
            doNotSend=result.doNotSend,
            dateReadiness=max(0, min(100, result.dateReadiness)),
            dateReadinessNote=result.dateReadinessNote,
            dateRecommendations=result.dateRecommendations or None,
            dateInvites=[_msg(m, style) for m in result.dateInvites] or None,
            urgencyWarning=result.urgencyWarning or None,
        )

    async def regenerate_message(
        self, *, message_text: str, instruction: str, tone: str
    ) -> GeneratedMessageDTO:
        """See :class:`AIClient`."""
        prompt = (
            f"Original message: {message_text!r}\n"
            f"Rewrite it per this instruction: {instruction!r}. Keep it natural and "
            "specific. Return the new text, a category, a 1-3 word label, and a "
            "cringeRisk 0-100."
        )
        result = await self._generate(contents=prompt, schema=_GeminiMessage)
        assert isinstance(result, _GeminiMessage)
        return _msg(result, normalise_tone(tone))


def build_ai_client(cfg: Config) -> AIClient:
    """Return the Gemini client (Vertex by default, AI Studio key otherwise)."""
    if not cfg.ai_use_vertex and not cfg.ai_api_key:
        logger.warning("No Gemini credentials configured — calls will fail.")
    return GeminiAIClient(cfg)
