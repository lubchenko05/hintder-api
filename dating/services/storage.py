"""Cloud Storage for uploaded screenshots.

Screenshots go to a dedicated GCS bucket (``storage_bucket``) under
``{prefix}/{user_id}/{read_id}/{i}.{ext}`` using a dedicated service account
(``storage_credentials_file``) — separate from Firebase/Vertex creds. Objects
are kept ``storage_retention_days`` (30) then auto-deleted by a bucket lifecycle
rule, not here (see ``scripts/set_storage_lifecycle.py``). The blocking GCS SDK
runs in a thread so it never stalls the event loop; uploads are best-effort.
"""

import asyncio
import base64
import logging
from datetime import timedelta
from typing import Any

from dating.config import Config

logger = logging.getLogger(__name__)

# How long a generated signed view URL stays valid (V4 caps at 7 days).
SIGNED_URL_TTL = timedelta(hours=1)


def _decode_image(data: str) -> tuple[bytes, str]:
    """Split a data-URL or raw base64 string into (bytes, mime_type)."""
    mime = "image/jpeg"
    payload = data
    if data.startswith("data:"):
        header, _, payload = data.partition(",")
        if ";" in header and ":" in header:
            mime = header.split(":", 1)[1].split(";", 1)[0] or mime
    return base64.b64decode(payload), mime


class StorageService:
    """Uploads read screenshots to the configured bucket (best-effort)."""

    def __init__(self, cfg: Config) -> None:
        """Capture config; the GCS client is created lazily on first use."""
        self._cfg = cfg
        self._client: Any = None

    @property
    def enabled(self) -> bool:
        """True when a storage bucket is configured."""
        return bool(self._cfg.storage_bucket)

    def _bucket(self) -> Any:
        """Return the GCS bucket handle, building the client once (own SA)."""
        from google.cloud import storage

        if self._client is None:
            if self._cfg.storage_credentials_file:
                from google.oauth2 import service_account

                creds = service_account.Credentials.from_service_account_file(
                    self._cfg.storage_credentials_file
                )
                self._client = storage.Client(project=creds.project_id, credentials=creds)
            else:
                # Application Default Credentials (e.g. Cloud Run runtime SA).
                self._client = storage.Client()
        return self._client.bucket(self._cfg.storage_bucket)

    async def upload_read_images(
        self, *, user_id: str, read_id: str, images: list[str]
    ) -> list[str]:
        """Upload screenshots and return their ``gs://`` URIs (empty on skip/fail)."""
        if not self.enabled or not images:
            return []
        try:
            return await asyncio.to_thread(self._upload, user_id, read_id, images)
        except Exception:
            # Storage is non-critical — never fail a read because an upload broke.
            logger.exception("Screenshot upload failed for user %s", user_id)
            return []

    def _upload(self, user_id: str, read_id: str, images: list[str]) -> list[str]:
        """Blocking upload of up to 6 images; returns their ``gs://`` URIs."""
        bucket = self._bucket()
        uris: list[str] = []
        for i, data in enumerate(images[:6]):
            raw, mime = _decode_image(data)
            ext = mime.split("/")[-1] or "jpg"
            blob = bucket.blob(f"{self._cfg.storage_prefix}/{user_id}/{read_id}/{i}.{ext}")
            blob.upload_from_string(raw, content_type=mime)
            uris.append(f"gs://{bucket.name}/{blob.name}")
        return uris

    async def signed_urls(self, *, user_id: str, uris: list[str]) -> list[str]:
        """Exchange this user's own ``gs://`` URIs for short-lived HTTPS view URLs.

        The bucket is private, so a saved match's screenshots can't be shown
        directly; the client passes back the stored ``gs://`` URIs and gets
        temporary signed GET URLs. URIs that don't live under this user's prefix
        are dropped (a user can only sign their own objects). Best-effort.
        """
        if not self.enabled or not uris:
            return []
        try:
            return await asyncio.to_thread(self._sign, user_id, uris)
        except Exception:
            logger.exception("Signing screenshot URLs failed for user %s", user_id)
            return []

    def _signing_kwargs(self) -> dict[str, Any]:
        """Extra ``generate_signed_url`` kwargs so V4 signing works on Cloud Run.

        With a local key file (``storage_credentials_file``) the blob signs
        itself. Under Application Default Credentials (the Cloud Run runtime SA,
        which has no private key) we sign through the IAM ``signBlob`` API by
        passing the SA email + a fresh access token — this needs the runtime SA
        to hold ``roles/iam.serviceAccountTokenCreator`` on itself.
        """
        if self._cfg.storage_credentials_file:
            return {}
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default()
        credentials.refresh(google.auth.transport.requests.Request())
        email = getattr(credentials, "service_account_email", None)
        if not email:
            return {}
        return {"service_account_email": email, "access_token": credentials.token}

    def _sign(self, user_id: str, uris: list[str]) -> list[str]:
        """Blocking V4 signing of up to 6 of the user's own ``gs://`` URIs."""
        bucket = self._bucket()
        prefix = f"gs://{bucket.name}/{self._cfg.storage_prefix}/{user_id}/"
        sign_kwargs = self._signing_kwargs()
        signed: list[str] = []
        for uri in uris[:6]:
            if not uri.startswith(prefix):
                continue  # not this user's object — refuse to sign
            blob_name = uri[len(f"gs://{bucket.name}/") :]
            blob = bucket.blob(blob_name)
            signed.append(
                blob.generate_signed_url(
                    version="v4",
                    expiration=SIGNED_URL_TTL,
                    method="GET",
                    **sign_kwargs,
                )
            )
        return signed
