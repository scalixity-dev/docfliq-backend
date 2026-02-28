"""
Async SMTP email delivery via aiosmtplib (primary provider).

Sends MIME-formatted HTML emails with STARTTLS.
Returns True on success, False on any failure (never raises).
"""
from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import Settings

logger = logging.getLogger(__name__)


def is_configured(settings: Settings) -> bool:
    """Return True when SMTP host and credentials are present."""
    return bool(settings.smtp_host and settings.smtp_username)


async def deliver(
    to_email: str,
    to_name: str,
    subject: str,
    html: str,
    settings: Settings,
) -> bool:
    """Send an HTML email via SMTP.  Returns True on success, False on failure."""
    if not is_configured(settings):
        return False

    msg = EmailMessage()
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = f"{to_name} <{to_email}>"
    msg["Subject"] = subject
    msg.set_content(html, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            start_tls=settings.smtp_start_tls,
            timeout=15,
        )
        return True
    except Exception as exc:
        logger.error("SMTP delivery failed (%s → %s): %s", settings.smtp_host, to_email, exc)
        return False
