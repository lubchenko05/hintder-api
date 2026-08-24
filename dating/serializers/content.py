"""Request validators and response models for the content API (guides/stories).

``PostUpsert`` is deliberately the *only* write shape: the import script, the
daily jobs and the admin all speak it, so there is one contract to keep honest
and one place where defaults and validation live.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from dating.models.content import CONTENT_KINDS, CONTENT_STATUSES, STATUS_DRAFT
from dating.serializers.base import BaseValidator

# The block types the frontend can render today. Only the envelope is checked —
# see the spec: mirroring eight discriminated unions here would mean a backend
# release every time a block grows a field.
BLOCK_TYPES = {
    "metrics",
    "opener",
    "thread",
    "quote",
    "opener-comparison",
    "workflow-drafts",
    "readiness-gauge",
    "timeline",
}


class PostUpsertValidator(BaseValidator):
    """The single write shape for a guide or story."""

    kind: str
    slug: str
    locale: str = "en"

    title: str
    seo_title: str | None = None
    subtitle: str | None = None
    excerpt: str = ""

    body_md: str | None = None
    body_html: str | None = None
    blocks: list[dict[str, Any]] | None = None

    category: str = ""
    persona: str | None = None
    read_time_minutes: int | None = None
    keywords: str | None = None

    status: str = STATUS_DRAFT
    published_at: datetime | None = None

    noindex: bool = False
    canonical_url: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None

    source: str = "automation"
    external_id: str | None = None
    author_name: str | None = None

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        """Reject a collection we don't serve."""
        if v not in CONTENT_KINDS:
            raise ValueError(f"kind must be one of {CONTENT_KINDS}")
        return v

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        """Reject a lifecycle state that doesn't exist."""
        if v not in CONTENT_STATUSES:
            raise ValueError(f"status must be one of {CONTENT_STATUSES}")
        return v

    @field_validator("slug")
    @classmethod
    def _slug_shape(cls, v: str) -> str:
        """Slugs are lowercase kebab-case — they end up in URLs."""
        cleaned = v.strip().lower()
        if not cleaned or not all(c.isalnum() or c == "-" for c in cleaned):
            raise ValueError("slug must be lowercase alphanumeric with hyphens")
        return cleaned

    @field_validator("blocks")
    @classmethod
    def _known_blocks(cls, v: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Every block must carry a type the frontend knows how to draw."""
        if v is None:
            return v
        for block in v:
            block_type = block.get("type")
            if block_type not in BLOCK_TYPES:
                raise ValueError(f"unknown block type: {block_type!r}")
        return v


class PostPatchValidator(BaseValidator):
    """Partial update. Every field optional; ``None`` means 'leave it alone'."""

    slug: str | None = None
    title: str | None = None
    seo_title: str | None = None
    subtitle: str | None = None
    excerpt: str | None = None
    body_md: str | None = None
    body_html: str | None = None
    blocks: list[dict[str, Any]] | None = None
    category: str | None = None
    persona: str | None = None
    read_time_minutes: int | None = None
    keywords: str | None = None
    status: str | None = None
    published_at: datetime | None = None
    noindex: bool | None = None
    canonical_url: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None


class PostListItemSerializer(BaseModel):
    """A post as it appears in a list — no body, so the payload stays small."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    slug: str
    title: str
    seo_title: str | None = None
    subtitle: str | None = None
    excerpt: str
    category: str
    persona: str | None = None
    read_time_minutes: int
    published_at: datetime | None = None
    updated_at: datetime


class PostSerializer(PostListItemSerializer):
    """A full post: everything a page needs to render and describe itself."""

    body_html: str
    body_md: str
    blocks: list[dict[str, Any]] | None = None
    keywords: str | None = None
    noindex: bool
    canonical_url: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    author_name: str | None = None


class AdminPostSerializer(PostSerializer):
    """The admin view — adds the fields only an operator cares about."""

    id: int
    status: str
    source: str
    external_id: str | None = None
    indexed_at: datetime | None = None
    created_at: datetime


class SitemapEntrySerializer(BaseModel):
    """One line of the sitemap feed."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    slug: str
    published_at: datetime | None = None
    updated_at: datetime


class RedirectSerializer(BaseModel):
    """Returned instead of a post when the slug has moved."""

    redirect_to: str


class UpsertResultSerializer(BaseModel):
    """What a write returns: where the post lives and whether it was new."""

    id: int
    kind: str
    slug: str
    url: str
    created: bool
    status: str
