"""One-time: set a 30-day delete lifecycle rule on the screenshots bucket.

Uploaded screenshots live under ``{storage_prefix}/`` (default ``reads/``) and
must auto-delete after ``storage_retention_days`` (30). GCS Object Lifecycle
Management does this server-side — no cron needed. Run once (re-running is
idempotent):

    python scripts/set_storage_lifecycle.py

Uses the same Vertex/Firebase service-account credentials the app uses, so the
SA needs ``storage.buckets.update`` on the bucket's project.
"""

import sys

from google.cloud import storage
from google.oauth2 import service_account

from dating.config import get_config


def main() -> int:
    """Apply the age-based delete rule (prefix-scoped) to the bucket."""
    cfg = get_config()
    if not cfg.storage_bucket:
        print("storage_bucket is empty — nothing to configure.")
        return 1

    if cfg.storage_credentials_file:
        credentials = service_account.Credentials.from_service_account_file(
            cfg.storage_credentials_file
        )
        client = storage.Client(project=credentials.project_id, credentials=credentials)
    else:
        client = storage.Client()
    bucket = client.bucket(cfg.storage_bucket)

    bucket.add_lifecycle_delete_rule(
        age=cfg.storage_retention_days,
        matches_prefix=[f"{cfg.storage_prefix}/"],
    )
    bucket.patch()
    print(
        f"Lifecycle set on gs://{cfg.storage_bucket}: delete objects under "
        f"'{cfg.storage_prefix}/' after {cfg.storage_retention_days} days."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
