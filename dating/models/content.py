"""The ``content_posts`` table — guides and success stories, served from the DB.

Content used to live as markdown in the frontend repo, which meant publishing a
post required a commit, a tag and a deploy. It lives here instead: the daily
jobs upsert through the admin API and the site renders whatever the API returns.

Two collections share this table (``kind``): guides and stories. Identity is
``(kind, slug)`` — the same slug may exist in both without colliding. Stories
additionally carry ``blocks``: the structured thread/opener/metrics/quote units
the frontend renders above the markdown body.
"""

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dating.models.base import Base
from dating.utils.datetime import utcnow

# Collections. Plain constants, not an Enum column, so adding one never needs a
# migration — same reasoning as the hint kinds.
KIND_GUIDES = "guides"
KIND_STORIES = "stories"
CONTENT_KINDS = (KIND_GUIDES, KIND_STORIES)

# Lifecycle. A post is visible only when published AND its time has come.
STATUS_DRAFT = "draft"
STATUS_SCHEDULED = "scheduled"
STATUS_PUBLISHED = "published"
STATUS_ARCHIVED = "archived"
CONTENT_STATUSES = (STATUS_DRAFT, STATUS_SCHEDULED, STATUS_PUBLISHED, STATUS_ARCHIVED)

# Where a row came from — useful when a job misbehaves and you need to tell
# machine-written rows from imported ones.
SOURCE_IMPORT = "repo-import"
SOURCE_AUTOMATION = "automation"
SOURCE_ADMIN = "admin"


class ContentPost(Base):
    """One guide or success story."""

    __tablename__ = "content_posts"
    __repr_attrs__ = ["id", "kind", "slug", "status"]

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)

    kind: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # One language today; the column exists so adding a second one later is a
    # data change rather than a migration of every query.
    locale: Mapped[str] = mapped_column(sa.String(10), nullable=False, default="en")

    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # A display title can run past the ~60 chars search engines show; when it
    # does, the post carries a shorter one for <title>.
    seo_title: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    subtitle: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    excerpt: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")

    body_md: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    # Rendered and sanitised on write, so a read is never a render.
    body_html: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    # Story blocks (thread / opener / metrics / quote), validated on the way in.
    # none_as_null: without it a Python ``None`` is stored as the JSON literal
    # ``null``, which is not SQL NULL — every future "where blocks is not null"
    # would then match guides that have no blocks at all.
    blocks: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )

    category: Mapped[str] = mapped_column(sa.String(120), nullable=False, default="")
    persona: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    read_time_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    keywords: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, default=STATUS_DRAFT)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    noindex: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    canonical_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    meta_title: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    meta_description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    source: Mapped[str] = mapped_column(sa.String(40), nullable=False, default=SOURCE_ADMIN)
    external_id: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    author_name: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utcnow
    )
    # Drives <lastmod> in the sitemap and dateModified in JSON-LD.
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    indexed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("kind", "slug", name="uq_content_posts_kind_slug"),
        sa.Index("ix_content_posts_kind_status_published", "kind", "status", "published_at"),
    )


class ContentSlugRedirect(Base):
    """A retired slug and where it now points, so old URLs keep working (301)."""

    __tablename__ = "content_slug_redirects"
    __repr_attrs__ = ["kind", "from_slug", "to_slug"]

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    from_slug: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    to_slug: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        sa.UniqueConstraint("kind", "from_slug", name="uq_content_redirects_kind_from"),
    )
