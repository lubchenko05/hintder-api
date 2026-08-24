"""Data access for ``ContentPost`` rows (guides and success stories)."""

from datetime import datetime
from typing import Any

import sqlalchemy as sa

from dating.models.content import (
    ContentPost,
    ContentSlugRedirect,
    STATUS_PUBLISHED,
)
from dating.storages.base import BaseStorage
from dating.utils.datetime import utcnow


def _visible() -> sa.ColumnElement[bool]:
    """The one definition of 'a visitor can see this'.

    Published *and* its publish time has passed — scheduled posts stay invisible
    until the clock catches up. Every public read goes through this so the site
    and the sitemap can never disagree about what exists.
    """
    return sa.and_(
        ContentPost.status == STATUS_PUBLISHED,
        ContentPost.published_at.isnot(None),
        ContentPost.published_at <= utcnow(),
    )


class ContentStorage(BaseStorage):
    """List / fetch / upsert content posts and their retired slugs."""

    # ── public reads ────────────────────────────────────────────────────

    async def list_visible(
        self,
        *,
        kind: str | None = None,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ContentPost]:
        """Visible posts, newest first."""
        stmt = sa.select(ContentPost).where(_visible())
        if kind:
            stmt = stmt.where(ContentPost.kind == kind)
        if category:
            stmt = stmt.where(ContentPost.category == category)
        stmt = stmt.order_by(ContentPost.published_at.desc()).limit(limit).offset(offset)
        async with self._session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_visible(self, kind: str, slug: str) -> ContentPost | None:
        """One visible post, or ``None``."""
        stmt = sa.select(ContentPost).where(
            ContentPost.kind == kind, ContentPost.slug == slug, _visible()
        )
        async with self._session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def sitemap_rows(self) -> list[ContentPost]:
        """Every visible post, light payload for the sitemap."""
        stmt = (
            sa.select(ContentPost)
            .where(_visible())
            .order_by(ContentPost.kind, ContentPost.published_at.desc())
        )
        async with self._session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def related(self, kind: str, slug: str, category: str, limit: int) -> list[ContentPost]:
        """Same-collection posts, preferring the same category."""
        stmt = (
            sa.select(ContentPost)
            .where(ContentPost.kind == kind, ContentPost.slug != slug, _visible())
            .order_by(
                (ContentPost.category == category).desc(),
                ContentPost.published_at.desc(),
            )
            .limit(limit)
        )
        async with self._session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ── admin ───────────────────────────────────────────────────────────

    async def list_all(
        self, *, kind: str | None = None, status: str | None = None, q: str | None = None
    ) -> list[ContentPost]:
        """Every post regardless of status — the admin view."""
        stmt = sa.select(ContentPost)
        if kind:
            stmt = stmt.where(ContentPost.kind == kind)
        if status:
            stmt = stmt.where(ContentPost.status == status)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(sa.or_(ContentPost.title.ilike(like), ContentPost.slug.ilike(like)))
        stmt = stmt.order_by(ContentPost.updated_at.desc())
        async with self._session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_by_id(self, post_id: int) -> ContentPost | None:
        """One post by primary key, any status."""
        async with self._session() as session:
            return await session.get(ContentPost, post_id)

    async def upsert(self, kind: str, slug: str, data: dict[str, Any]) -> tuple[ContentPost, bool]:
        """Insert or update by ``(kind, slug)``. Returns ``(post, created)``.

        Identity is the pair, so a job that runs twice updates one row instead
        of writing a second one.
        """
        async with self._begin() as session:
            post = await session.scalar(
                sa.select(ContentPost)
                .where(ContentPost.kind == kind, ContentPost.slug == slug)
                .with_for_update()
            )
            created = post is None
            if post is None:
                post = ContentPost(kind=kind, slug=slug, **data)
                session.add(post)
            else:
                for key, value in data.items():
                    setattr(post, key, value)
            await session.flush()
            await session.refresh(post)
            return post, created

    async def update(self, post_id: int, data: dict[str, Any]) -> ContentPost | None:
        """Patch one post in place."""
        async with self._begin() as session:
            post = await session.get(ContentPost, post_id, with_for_update=True)
            if post is None:
                return None
            for key, value in data.items():
                setattr(post, key, value)
            await session.flush()
            await session.refresh(post)
            return post

    async def mark_indexed(self, post_id: int, when: datetime | None = None) -> None:
        """Record a successful submission to the search engines."""
        async with self._begin() as session:
            post = await session.get(ContentPost, post_id)
            if post is not None:
                post.indexed_at = when or utcnow()

    async def due_scheduled(self) -> list[ContentPost]:
        """Scheduled posts whose time has come — the cron's work list."""
        stmt = sa.select(ContentPost).where(
            ContentPost.status == "scheduled",
            ContentPost.published_at.isnot(None),
            ContentPost.published_at <= utcnow(),
        )
        async with self._session() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ── redirects ───────────────────────────────────────────────────────

    async def add_redirect(self, kind: str, from_slug: str, to_slug: str) -> None:
        """Point a retired slug at its replacement (idempotent)."""
        async with self._begin() as session:
            existing = await session.scalar(
                sa.select(ContentSlugRedirect).where(
                    ContentSlugRedirect.kind == kind,
                    ContentSlugRedirect.from_slug == from_slug,
                )
            )
            if existing is None:
                session.add(ContentSlugRedirect(kind=kind, from_slug=from_slug, to_slug=to_slug))
            else:
                existing.to_slug = to_slug

    async def redirect_for(self, kind: str, slug: str) -> str | None:
        """Where a retired slug should send the visitor, if anywhere."""
        stmt = sa.select(ContentSlugRedirect.to_slug).where(
            ContentSlugRedirect.kind == kind, ContentSlugRedirect.from_slug == slug
        )
        async with self._session() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
