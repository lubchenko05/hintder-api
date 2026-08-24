"""Auth for machine callers (the daily content jobs).

The jobs are not users: they have no Firebase identity and no JWT. They present
a shared key that unlocks ``/admin/content/*`` and nothing else, so a leaked key
cannot touch users, matches or billing. The key lives in Secret Manager and can
be rotated without a release.
"""

import hmac

from fastapi import Header

from dating.config import get_config
from dating.utils.error_handler import UnauthorizedException


def require_automation_key(x_automation_key: str | None = Header(default=None)) -> None:
    """Accept the request only if it carries the configured automation key."""
    configured = get_config().content_automation_key
    if not configured:
        # Refuse rather than fall open: an unset key must not mean "public".
        raise UnauthorizedException("Automation key is not configured")
    if not x_automation_key or not hmac.compare_digest(x_automation_key, configured):
        raise UnauthorizedException("Invalid automation key")
