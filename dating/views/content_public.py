"""Public read API for guides and stories — what the site renders from.

No authentication: these are the pages themselves. Responses carry cache headers
so the CDN and Next.js can serve them stale while revalidating, which is what
keeps the site up when this API is not.
"""

from fastapi import APIRouter, Depends, Query, Response

from dating.bl import content as bl_content
from dating.dependencies.inj import get_db_storage
from dating.serializers.content import (
    PostListItemSerializer,
    PostSerializer,
    SitemapEntrySerializer,
)
from dating.storages import DBStorage
from dating.utils.error_handler import NotFoundException

router = APIRouter()

# Five minutes fresh, a day of stale-while-revalidate: a reader never waits for
# our database, and a publish still lands quickly via on-demand revalidation.
_CACHE = "public, s-maxage=300, stale-while-revalidate=86400"


@router.get("/public/content/posts", response_model=list[PostListItemSerializer], tags=["content"])
async def list_posts(
    response: Response,
    kind: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: DBStorage = Depends(get_db_storage),
) -> list[PostListItemSerializer]:
    """Visible posts, newest first, without bodies."""
    response.headers["Cache-Control"] = _CACHE
    posts = await db.content.list_visible(kind=kind, category=category, limit=limit, offset=offset)
    return [PostListItemSerializer.model_validate(p) for p in posts]


@router.get(
    "/public/content/sitemap", response_model=list[SitemapEntrySerializer], tags=["content"]
)
async def sitemap(
    response: Response, db: DBStorage = Depends(get_db_storage)
) -> list[SitemapEntrySerializer]:
    """Every visible post — the feed the frontend's sitemap.xml is built from."""
    response.headers["Cache-Control"] = _CACHE
    rows = await db.content.sitemap_rows()
    return [SitemapEntrySerializer.model_validate(r) for r in rows]


@router.get(
    "/public/content/related/{kind}/{slug}",
    response_model=list[PostListItemSerializer],
    tags=["content"],
)
async def related(
    kind: str,
    slug: str,
    response: Response,
    limit: int = Query(default=3, le=12),
    db: DBStorage = Depends(get_db_storage),
) -> list[PostListItemSerializer]:
    """Posts to read next — same collection, same category first."""
    response.headers["Cache-Control"] = _CACHE
    post = await db.content.get_visible(kind, slug)
    category = post.category if post else ""
    rows = await db.content.related(kind, slug, category, limit)
    return [PostListItemSerializer.model_validate(r) for r in rows]


@router.get("/public/content/posts/{kind}/{slug}", tags=["content"])
async def get_post(
    kind: str, slug: str, response: Response, db: DBStorage = Depends(get_db_storage)
) -> dict[str, object]:
    """One visible post.

    A retired slug answers 200 with ``redirect_to`` instead of 404 so the
    frontend can issue a real 301 and keep the link equity.
    """
    response.headers["Cache-Control"] = _CACHE
    post = await db.content.get_visible(kind, slug)
    if post is not None:
        return PostSerializer.model_validate(post).model_dump(mode="json")

    moved_to = await db.content.redirect_for(kind, slug)
    if moved_to:
        return {"redirect_to": bl_content.post_path(kind, moved_to)}

    raise NotFoundException("Post not found")
