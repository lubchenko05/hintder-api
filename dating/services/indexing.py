"""Search-engine indexing — IndexNow + Google Indexing API.

Lives on the backend so publishing indexes itself: the daily jobs used to
submit URLs after waiting out a deploy, which meant indexing depended on the
job's machine, its gcloud login and its patience. Now it is a side effect of
the publish, recorded in ``indexed_at``.

Google auth is service-account **impersonation** (no key files): the Cloud Run
runtime SA mints a token for ``seeto-api@seeto-315cd``, which is a verified
Owner of ``sc-domain:hintder.ai`` in Search Console. That SA predates Google's
2026 bug with newly created service accounts — the same workaround the jobs
used, moved server-side.
"""

import asyncio
import logging

import httpx

from dating.config import get_config

logger = logging.getLogger(__name__)

_INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
_GOOGLE_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
_GOOGLE_SCOPE = "https://www.googleapis.com/auth/indexing"

URL_UPDATED = "URL_UPDATED"
URL_DELETED = "URL_DELETED"


def _google_token() -> str | None:
    """Mint an indexing-scoped token for the Search Console owner SA.

    Blocking (google-auth is sync) — call it via ``asyncio.to_thread``.
    Returns ``None`` when credentials aren't available, e.g. locally.
    """
    try:
        import google.auth
        from google.auth.impersonated_credentials import Credentials as Impersonated
        from google.auth.transport.requests import Request

        source, _ = google.auth.default()
        target = Impersonated(
            source_credentials=source,
            target_principal=get_config().google_indexing_sa,
            target_scopes=[_GOOGLE_SCOPE],
            lifetime=300,
        )
        target.refresh(Request())
        return str(target.token)
    except Exception:
        logger.exception("Google indexing: could not mint an impersonated token")
        return None


async def submit_indexnow(urls: list[str]) -> int | None:
    """One batched IndexNow ping for the given URLs. Returns the HTTP status."""
    cfg = get_config()
    host = cfg.frontend_base_url.replace("https://", "").replace("http://", "").strip("/")
    payload = {
        "host": host,
        "key": cfg.indexnow_key,
        "keyLocation": f"{cfg.frontend_base_url.rstrip('/')}/{cfg.indexnow_key}.txt",
        "urlList": urls,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(_INDEXNOW_ENDPOINT, json=payload)
        return resp.status_code
    except Exception:
        logger.exception("IndexNow submission failed for %s", urls)
        return None


async def submit_google(url: str, notification_type: str) -> int | None:
    """Notify Google about one URL. Returns the HTTP status, ``None`` on error."""
    token = await asyncio.to_thread(_google_token)
    if token is None:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                _GOOGLE_ENDPOINT,
                json={"url": url, "type": notification_type},
                headers={"Authorization": f"Bearer {token}"},
            )
        return resp.status_code
    except Exception:
        logger.exception("Google indexing submission failed for %s", url)
        return None
