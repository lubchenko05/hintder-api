"""Business logic for guides and success stories.

Everything that writes content funnels through :func:`upsert_post`: it renders
markdown once, sanitises it, fills in what the caller left out (read time,
publish time), records a redirect when a slug moves, and then asks the frontend
to drop its caches. Views, the import script and the daily jobs all call this —
so a post published by a job is identical to one published by hand.
"""

import asyncio
import logging
from typing import Any

from dating.config import get_config
from dating.models.content import (
    ContentPost,
    KIND_GUIDES,
    STATUS_PUBLISHED,
)
from dating.services import indexing
from dating.services.markdown import (
    estimate_read_minutes,
    render_markdown,
    sanitize_html,
)
from dating.storages import DBStorage
from dating.utils.datetime import utcnow

logger = logging.getLogger(__name__)


def post_path(kind: str, slug: str) -> str:
    """The site path a post lives at. One definition, used by URLs and revalidation."""
    return f"/{kind}/{slug}"


def post_url(kind: str, slug: str) -> str:
    """The absolute URL of a post."""
    base = get_config().frontend_base_url.rstrip("/")
    return f"{base}{post_path(kind, slug)}"


def _prepare(data: dict[str, Any]) -> dict[str, Any]:
    """Fill in the derived fields a caller shouldn't have to compute.

    Rendering happens here rather than on read: a page view should never pay for
    a markdown parse, and storing the HTML means the sanitiser ran before the
    content was ever persisted.
    """
    body_md = data.get("body_md") or ""
    body_html = data.get("body_html")

    if body_html:
        # Already-rendered HTML (an admin paste, later a webhook) still goes
        # through the allowlist — it is the only security boundary we have.
        data["body_html"] = sanitize_html(body_html)
    else:
        data["body_html"] = render_markdown(body_md)
    data["body_md"] = body_md

    if not data.get("read_time_minutes"):
        data["read_time_minutes"] = estimate_read_minutes(body_md)

    # Publishing without a timestamp means "now" — otherwise the post would be
    # published and invisible, which is the most confusing state there is.
    if data.get("status") == STATUS_PUBLISHED and data.get("published_at") is None:
        data["published_at"] = utcnow()

    return data


async def upsert_post(
    db: DBStorage, *, kind: str, slug: str, data: dict[str, Any]
) -> tuple[ContentPost, bool]:
    """Create or update a post by ``(kind, slug)``; returns ``(post, created)``."""
    prepared = _prepare(dict(data))
    post, created = await db.content.upsert(kind, slug, prepared)
    await revalidate(kind, slug)
    return post, created


async def patch_post(db: DBStorage, *, post_id: int, data: dict[str, Any]) -> ContentPost | None:
    """Partially update a post, recording a redirect if its slug changed."""
    existing = await db.content.get_by_id(post_id)
    if existing is None:
        return None

    old_slug = existing.slug
    new_slug = data.get("slug") or old_slug

    # Re-render only when the body actually changed, so a title edit doesn't
    # rewrite HTML that was fine.
    if "body_md" in data or "body_html" in data:
        merged = {
            "body_md": data.get("body_md", existing.body_md),
            "body_html": data.get("body_html"),
            "read_time_minutes": data.get("read_time_minutes"),
            "status": data.get("status", existing.status),
            "published_at": data.get("published_at", existing.published_at),
        }
        prepared = _prepare(merged)
        data["body_md"] = prepared["body_md"]
        data["body_html"] = prepared["body_html"]
        data["read_time_minutes"] = prepared["read_time_minutes"]

    post = await db.content.update(post_id, data)
    if post is None:
        return None

    if new_slug != old_slug:
        # The old URL is already indexed and possibly linked to; it must keep
        # resolving, so it becomes a 301 rather than a 404.
        await db.content.add_redirect(existing.kind, old_slug, new_slug)
        await revalidate(existing.kind, old_slug)

    await revalidate(post.kind, post.slug)
    return post


async def set_published(db: DBStorage, *, post_id: int, published: bool) -> ContentPost | None:
    """Publish or unpublish, then refresh the site's caches."""
    existing = await db.content.get_by_id(post_id)
    if existing is None:
        return None
    data: dict[str, Any] = {"status": STATUS_PUBLISHED if published else "draft"}
    if published and existing.published_at is None:
        data["published_at"] = utcnow()
    post = await db.content.update(post_id, data)
    if post is not None:
        await revalidate(post.kind, post.slug)
        await submit_to_indexes(db, post, deleted=not published, announce=published)
    return post


async def archive_post(db: DBStorage, *, post_id: int) -> ContentPost | None:
    """Soft-delete: the page 404s and drops out of the sitemap, the row stays."""
    existing = await db.content.get_by_id(post_id)
    if existing is None:
        return None
    post = await db.content.update(post_id, {"status": "archived"})
    if post is not None:
        await revalidate(post.kind, post.slug)
        # Tell Google the URL is gone so it drops out instead of going stale.
        await submit_to_indexes(db, post, deleted=True, announce=False)
    return post


async def publish_due_scheduled(db: DBStorage) -> list[ContentPost]:
    """Flip scheduled posts whose time has come. Called by a cron each minute."""
    due = await db.content.due_scheduled()
    published: list[ContentPost] = []
    for post in due:
        updated = await db.content.update(post.id, {"status": STATUS_PUBLISHED})
        if updated is not None:
            published.append(updated)
            await revalidate(updated.kind, updated.slug)
            await submit_to_indexes(db, updated, deleted=False, announce=True)
    return published


async def revalidate(kind: str, slug: str) -> None:
    """Ask the frontend to drop the cached page, its list and the sitemap.

    Best effort by design: a failed revalidation must never undo a publish. The
    content is already in the database, so the worst case is that it appears
    after the ISR TTL instead of within seconds.
    """
    cfg = get_config()
    if not cfg.revalidate_secret or not cfg.frontend_base_url:
        logger.info("Revalidation skipped — no secret or frontend URL configured")
        return

    import httpx  # local: keeps the import cost off the hot path

    payload = {
        "tags": ["content", f"content:{kind}:{slug}"],
        "paths": [post_path(kind, slug), f"/{kind}", "/sitemap.xml"],
    }
    url = f"{cfg.frontend_base_url.rstrip('/')}/api/revalidate"

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    url, json=payload, headers={"X-Revalidate-Secret": cfg.revalidate_secret}
                )
            if resp.status_code < 400:
                return
            logger.warning("Revalidation returned %s for %s", resp.status_code, url)
        except Exception:
            logger.warning("Revalidation attempt %s failed for %s", attempt + 1, url)
        await asyncio.sleep(0.5 * (attempt + 1))

    logger.error("Revalidation gave up for %s/%s — page appears after TTL", kind, slug)


def default_kind() -> str:
    """The collection assumed when a caller omits one."""
    return KIND_GUIDES


async def submit_to_indexes(
    db: DBStorage, post: ContentPost, *, deleted: bool, announce: bool
) -> tuple[int | None, int | None]:
    """Submit a post's URL to IndexNow and Google; best effort, never raises.

    Runs synchronously inside the admin request on purpose: there is no worker,
    and Cloud Run throttles CPU once the response is sent, so a fire-and-forget
    task would starve. The extra ~2 s lands on the jobs, not on users.

    Skipped entirely when indexing is disabled (local/dev), when the post is
    ``noindex``, and for ``repo-import`` rows — a re-import of 93 posts must not
    burn the daily Google quota or spam the operator.
    """
    cfg = get_config()
    if not cfg.indexing_enabled or post.noindex or post.source == "repo-import":
        return None, None

    url = post_url(post.kind, post.slug)
    notification = indexing.URL_DELETED if deleted else indexing.URL_UPDATED

    indexnow_code: int | None = None
    google_code: int | None = None
    try:
        indexnow_code = await indexing.submit_indexnow([url])
        google_code = await indexing.submit_google(url, notification)
        ok = any(code is not None and code < 300 for code in (indexnow_code, google_code))
        if ok and not deleted:
            await db.content.mark_indexed(post.id)
        if not ok:
            logger.error(
                "Indexing failed for %s (indexnow=%s google=%s)", url, indexnow_code, google_code
            )
    except Exception:
        logger.exception("Indexing blew up for %s", url)

    if announce and not deleted:
        try:
            from dating.services.telegram import notify_content_published

            await notify_content_published(
                kind=post.kind,
                title=post.title,
                url=url,
                indexnow=indexnow_code,
                google=google_code,
            )
        except Exception:
            logger.exception("Telegram publish alert failed for %s", url)

    return indexnow_code, google_code
