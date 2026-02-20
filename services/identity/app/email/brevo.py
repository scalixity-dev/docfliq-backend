"""
Brevo (Sendinblue) REST API email delivery (fallback provider).

Returns True on success, False on any failure (never raises).
"""
from __future__ import annotations

import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)
_BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def is_configured(settings: Settings) -> bool:
    """Return True when the Brevo API key is present."""
    return bool(settings.brevo_api_key)


async def deliver(
    to_email: str,
    to_name: str,
    subject: str,
    html: str,
    settings: Settings,
) -> bool:
    """Send an HTML email via Brevo REST API.  Returns True on success, False on failure."""
    if not is_configured(settings):
        return False

    payload = {
        "sender": {"email": settings.brevo_from_email, "name": settings.brevo_from_name},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                _BREVO_URL,
                json=payload,
                headers={"api-key": settings.brevo_api_key, "Content-Type": "application/json"},
            )
        if r.status_code >= 400:
            logger.error("Brevo error %s: %s", r.status_code, r.text[:300])
            return False
        return True
    except httpx.HTTPError as exc:
        logger.error("Brevo request failed: %s", exc)
        return False
