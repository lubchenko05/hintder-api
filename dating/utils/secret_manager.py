"""GCP Secret Manager resolution for production (Cloud Run).

In dev/test this is a no-op: ``access_secret_version`` returns ``None`` so the
caller falls back to env vars / defaults. In prod the GCP project is read from
``GOOGLE_CLOUD_PROJECT`` and secrets are pulled by name. Import of the GCP SDK
is lazy so local dev never needs the dependency installed.
"""

import logging
import os

logger = logging.getLogger(__name__)


def access_secret_version(secret_name: str, version: str = "latest") -> str | None:
    """Fetch a secret payload from GCP Secret Manager, or ``None`` if unavailable.

    Returns ``None`` (rather than raising) when the project isn't configured or
    the SDK isn't installed, so config resolution degrades gracefully to env
    vars and defaults in local development.
    """
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        return None
    try:
        from google.cloud import secretmanager
    except ImportError:
        logger.debug("google-cloud-secret-manager not installed; skipping %s", secret_name)
        return None
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/{version}"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("utf-8")
    except Exception:
        logger.warning("Could not access secret %s from Secret Manager", secret_name)
        return None
