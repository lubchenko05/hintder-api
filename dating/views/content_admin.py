"""Admin / automation API for guides and stories.

Guarded by the automation key (the daily jobs) — the same endpoints an admin UI
would use later. Every write goes through ``bl.content``, so rendering,
sanitisation, redirects and cache revalidation happen no matter who called.
"""

from fastapi import APIRouter, Depends, Query

from dating.bl import content as bl_content
from dating.dependencies.automation import require_automation_key
from dating.dependencies.inj import get_db_storage
from dating.serializers.content import (
    AdminPostSerializer,
    PostPatchValidator,
    PostUpsertValidator,
    UpsertResultSerializer,
)
from dating.storages import DBStorage
from dating.utils.error_handler import NotFoundException

router = APIRouter(dependencies=[Depends(require_automation_key)])


@router.get(
    "/admin/content/posts", response_model=list[AdminPostSerializer], tags=["content-admin"]
)
async def list_posts(
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: DBStorage = Depends(get_db_storage),
) -> list[AdminPostSerializer]:
    """Every post, any status — what the job reads to see what already exists."""
    posts = await db.content.list_all(kind=kind, status=status, q=q)
    return [AdminPostSerializer.model_validate(p) for p in posts]


@router.post("/admin/content/posts", response_model=UpsertResultSerializer, tags=["content-admin"])
async def upsert_post(
    payload: PostUpsertValidator, db: DBStorage = Depends(get_db_storage)
) -> UpsertResultSerializer:
    """Create or update a post by ``(kind, slug)`` — the jobs' single call."""
    data = payload.model_dump(exclude={"kind", "slug"})
    post, created = await bl_content.upsert_post(
        db, kind=payload.kind, slug=payload.slug, data=data
    )
    return UpsertResultSerializer(
        id=post.id,
        kind=post.kind,
        slug=post.slug,
        url=bl_content.post_url(post.kind, post.slug),
        created=created,
        status=post.status,
    )


@router.patch(
    "/admin/content/posts/{post_id}", response_model=AdminPostSerializer, tags=["content-admin"]
)
async def patch_post(
    post_id: int, payload: PostPatchValidator, db: DBStorage = Depends(get_db_storage)
) -> AdminPostSerializer:
    """Partial update; changing the slug leaves a 301 behind."""
    data = payload.model_dump(exclude_none=True)
    post = await bl_content.patch_post(db, post_id=post_id, data=data)
    if post is None:
        raise NotFoundException("Post not found")
    return AdminPostSerializer.model_validate(post)


@router.post(
    "/admin/content/posts/{post_id}/publish",
    response_model=AdminPostSerializer,
    tags=["content-admin"],
)
async def publish_post(
    post_id: int, db: DBStorage = Depends(get_db_storage)
) -> AdminPostSerializer:
    """Make a post visible now."""
    post = await bl_content.set_published(db, post_id=post_id, published=True)
    if post is None:
        raise NotFoundException("Post not found")
    return AdminPostSerializer.model_validate(post)


@router.post(
    "/admin/content/posts/{post_id}/unpublish",
    response_model=AdminPostSerializer,
    tags=["content-admin"],
)
async def unpublish_post(
    post_id: int, db: DBStorage = Depends(get_db_storage)
) -> AdminPostSerializer:
    """Pull a post back to draft."""
    post = await bl_content.set_published(db, post_id=post_id, published=False)
    if post is None:
        raise NotFoundException("Post not found")
    return AdminPostSerializer.model_validate(post)


@router.post(
    "/admin/content/posts/{post_id}/reindex",
    response_model=AdminPostSerializer,
    tags=["content-admin"],
)
async def reindex_post(
    post_id: int, db: DBStorage = Depends(get_db_storage)
) -> AdminPostSerializer:
    """Push one post back through IndexNow + Google — the manual retry path.

    Needed whenever a publish reached the site but not the engines: the head
    verification refused it, or the post predates the wiring that submits on
    upsert.
    """
    post = await db.content.get_by_id(post_id)
    if post is None:
        raise NotFoundException("Post not found")
    await bl_content.submit_to_indexes(db, post, deleted=False, announce=False)
    refreshed = await db.content.get_by_id(post_id)
    return AdminPostSerializer.model_validate(refreshed)


@router.delete(
    "/admin/content/posts/{post_id}", response_model=AdminPostSerializer, tags=["content-admin"]
)
async def archive_post(
    post_id: int, db: DBStorage = Depends(get_db_storage)
) -> AdminPostSerializer:
    """Soft delete — the page 404s and leaves the sitemap; the row survives."""
    post = await bl_content.archive_post(db, post_id=post_id)
    if post is None:
        raise NotFoundException("Post not found")
    return AdminPostSerializer.model_validate(post)
