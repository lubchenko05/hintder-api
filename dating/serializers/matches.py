"""Match request validators + response serializer (camelCase round-trip)."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from dating.serializers.base import BaseSerializer, BaseValidator


class ConvTurn(BaseModel):
    """One conversation turn. Extra keys (e.g. transient screenshots) are dropped."""

    model_config = ConfigDict(extra="ignore")

    id: str
    role: str
    text: str
    ts: int


class MatchUpsertValidator(BaseValidator):
    """``PUT /matches/{id}`` body — the full match to create or replace."""

    name: str
    age: int = 0
    status: str = "in_progress"
    analysis: dict[str, Any]
    conversation: list[ConvTurn] = []
    messages: list[dict[str, Any]] = []
    followUp: dict[str, Any] | None = None
    pickedStyle: str | None = None
    pickedTone: str | None = None
    createdAt: int
    updatedAt: int


class MatchSerializer(BaseSerializer):
    """A persisted match, shaped exactly like the frontend ``MatchHistoryEntry``."""

    id: str
    name: str
    age: int
    status: str
    analysis: dict[str, Any]
    conversation: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    followUp: dict[str, Any] | None
    pickedStyle: str | None
    pickedTone: str | None
    createdAt: int
    updatedAt: int
