"""Transactional email via the Brevo (Sendinblue) API.

A thin async wrapper over ``POST https://api.brevo.com/v3/smtp/email`` used to
send auth magic-link emails from our own domain (``noreply@hintder.ai``), so
they're branded and DKIM-aligned instead of going through Firebase's default
sender. Best-effort: a send failure is logged, never raised at the caller.
"""

import logging

import httpx

from dating.config import Config

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


class EmailService:
    """Sends HTML emails through the Brevo API (no-op until a key is set)."""

    def __init__(self, cfg: Config) -> None:
        """Capture config; the HTTP client is created per-send (short-lived)."""
        self._cfg = cfg

    @property
    def enabled(self) -> bool:
        """True once a Brevo API key is configured."""
        return self._cfg.brevo_enabled

    async def send_html(self, *, to: str, subject: str, html: str) -> bool:
        """Send one HTML email; return whether Brevo accepted it (best-effort)."""
        if not self.enabled:
            logger.warning("Brevo not configured — skipping email to %s", to)
            return False
        payload = {
            "sender": {"name": self._cfg.brevo_from_name, "email": self._cfg.brevo_from_email},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    BREVO_API_URL,
                    json=payload,
                    headers={"api-key": self._cfg.brevo_api_key, "Content-Type": "application/json"},
                )
            if resp.status_code in (200, 201):
                logger.info("Email sent to %s: %s", to, subject)
                return True
            logger.error("Brevo error %s for %s: %s", resp.status_code, to, resp.text)
            return False
        except Exception:
            logger.exception("Failed to send email to %s", to)
            return False
