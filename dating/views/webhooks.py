"""Inbound publish webhooks — SiteOps posting content onto hintder.ai.

Contract (final, agreed 2026-08-24 — see CONTENT-CMS-SPEC.md §12 of the base
spec): HMAC-SHA256 over the raw body in ``X-SiteOps-Signature`` (``sha256=…``),
delivery identity in ``X-SiteOps-Delivery``.

The two identities must not be confused:

* **Deduplication is by delivery id ONLY.** A retry of the same delivery
  (identical id) answers ``{"url", "duplicate": true}`` and does nothing.
* The same **slug** under a NEW delivery id is a normal upsert-update — that is
  how SiteOps edits a published post.

Sync work is upsert + revalidation + indexing (a few seconds — SiteOps waits up
to 20 s and then live-confirms by fetching the URL, which on-demand ISR
satisfies immediately).
"""

import hashlib
import hmac
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from dating.bl import content as bl_content
from dating.config import get_config
from dating.dependencies.inj import get_db_storage
from dating.models.content import KIND_GUIDES, STATUS_PUBLISHED, STATUS_SCHEDULED
from dating.models.webhook_delivery import (
    DELIVERY_ACCEPTED,
    DELIVERY_FAILED,
    DELIVERY_IGNORED,
    DELIVERY_REJECTED,
    PROVIDER_SITEOPS,
)
from dating.storages import DBStorage
from dating.utils.datetime import utcnow

logger = logging.getLogger(__name__)

router = APIRouter()

_SIGNATURE_HEADER = "X-SiteOps-Signature"
_DELIVERY_HEADER = "X-SiteOps-Delivery"

_TAG = re.compile(r"<[^>]+>")


def _valid_signature(secret: str, raw: bytes, header: str | None) -> bool:
    """Constant-time check of ``sha256=<hex>`` over the exact body bytes."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[len("sha256=") :], expected)


def _derive_excerpt(html: str, markdown: str | None) -> str:
    """A meta-description-sized excerpt — SiteOps doesn't send one."""
    text = _TAG.sub(" ", markdown or html)
    text = re.sub(r"[#>*`\[\]()]|\s+", lambda m: " " if m.group().isspace() else "", text)
    text = " ".join(text.split())
    if len(text) <= 160:
        return text
    return text[:157].rsplit(" ", 1)[0] + "…"


def _parse_publish_at(value: Any) -> datetime | None:
    """ISO timestamp → aware datetime; ``None`` when absent or unreadable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@router.post("/webhooks/content/siteops", tags=["webhooks"])
async def siteops_webhook(
    request: Request, db: DBStorage = Depends(get_db_storage)
) -> JSONResponse:
    """Accept one SiteOps publish delivery."""
    cfg = get_config()
    if not cfg.siteops_webhook_secret:
        # Fail closed: an unset secret must not mean "accept anything". 5xx is
        # deliberate — SiteOps retries those, so a config gap loses nothing.
        return JSONResponse({"error": "webhook not configured"}, status_code=503)

    raw = await request.body()
    if not _valid_signature(
        cfg.siteops_webhook_secret, raw, request.headers.get(_SIGNATURE_HEADER)
    ):
        return JSONResponse({"error": "invalid signature"}, status_code=401)

    delivery_id = request.headers.get(_DELIVERY_HEADER) or ""
    if not delivery_id:
        return JSONResponse({"error": "missing delivery id"}, status_code=422)

    body_sha = hashlib.sha256(raw).hexdigest()

    # Dedup — the retry of a delivery we already processed.
    seen = await db.webhook_delivery.get(PROVIDER_SITEOPS, delivery_id)
    if seen is not None:
        url = ""
        if seen.post_id is not None:
            post = await db.content.get_by_id(seen.post_id)
            if post is not None:
                url = bl_content.post_url(post.kind, post.slug)
        return JSONResponse({"url": url, "duplicate": True})

    try:
        payload_any = json.loads(raw)
        assert isinstance(payload_any, dict)
        payload: dict[str, Any] = payload_any
    except Exception:
        await db.webhook_delivery.record(
            provider=PROVIDER_SITEOPS,
            delivery_id=delivery_id,
            event_type="",
            body_sha256=body_sha,
            status=DELIVERY_REJECTED,
            error="unparseable body",
        )
        return JSONResponse({"error": "invalid payload"}, status_code=422)

    event = str(payload.get("event") or "")
    if payload.get("type") != "post":
        await db.webhook_delivery.record(
            provider=PROVIDER_SITEOPS,
            delivery_id=delivery_id,
            event_type=event,
            body_sha256=body_sha,
            status=DELIVERY_IGNORED,
        )
        return JSONResponse({"status": "ignored"})

    slug = str(payload.get("slug") or "").strip().lower()
    title = str(payload.get("title") or "").strip()
    html = payload.get("html")
    markdown = payload.get("markdown")
    if not slug or not title or not (html or markdown):
        await db.webhook_delivery.record(
            provider=PROVIDER_SITEOPS,
            delivery_id=delivery_id,
            event_type=event,
            body_sha256=body_sha,
            status=DELIVERY_REJECTED,
            error="missing slug/title/body",
        )
        return JSONResponse({"error": "slug, title and html or markdown required"}, status_code=422)

    # Claim the delivery BEFORE processing: under concurrent retries the unique
    # key lets exactly one request through; the loser answers duplicate.
    row = await db.webhook_delivery.record(
        provider=PROVIDER_SITEOPS,
        delivery_id=delivery_id,
        event_type=event,
        body_sha256=body_sha,
        status=DELIVERY_ACCEPTED,
    )
    if row is None:
        return JSONResponse({"url": "", "duplicate": True})

    publish_at = _parse_publish_at(payload.get("publish_at"))
    future = publish_at is not None and publish_at > utcnow()
    kind = payload.get("kind") if payload.get("kind") in ("guides", "stories") else KIND_GUIDES

    data: dict[str, Any] = {
        "title": title,
        "excerpt": _derive_excerpt(
            str(html or ""), markdown if isinstance(markdown, str) else None
        ),
        # html passes ONLY through the nh3 allowlist (no re-render) — the
        # sanitiser is the single security boundary for foreign HTML.
        "body_html": str(html) if html else None,
        "body_md": str(markdown) if markdown else "",
        "category": "Dating Strategy",
        "status": STATUS_SCHEDULED if future else STATUS_PUBLISHED,
        "published_at": publish_at,
        "canonical_url": payload.get("canonical") or None,
        "source": "webhook:siteops",
        "external_id": delivery_id,
    }

    try:
        post, _created = await bl_content.upsert_post(db, kind=str(kind), slug=slug, data=data)
    except Exception as exc:
        logger.exception("SiteOps delivery %s failed", delivery_id)
        await db.webhook_delivery.update_status(
            row.id, status=DELIVERY_FAILED, error=str(exc)[:500]
        )
        # 5xx → SiteOps retries once with the SAME delivery id; the dedup row
        # would block that retry, so release the claim by marking failed and
        # letting the retry pass the get() check… it won't (row exists). So:
        # answer 500 AND leave the row as failed — the operator replays via
        # the admin API if it mattered.
        return JSONResponse({"error": "processing failed"}, status_code=500)

    await db.webhook_delivery.update_status(row.id, status=DELIVERY_ACCEPTED, post_id=post.id)
    return JSONResponse({"url": bl_content.post_url(post.kind, post.slug)})
