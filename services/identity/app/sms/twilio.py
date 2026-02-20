"""
Twilio Verify V2 — async OTP delivery and verification via httpx.

Uses Twilio's managed Verify service: OTP generation, SMS delivery, and
code verification are handled entirely by Twilio.  We never store
Twilio-managed OTPs in Redis/PostgreSQL — Twilio owns the lifecycle.

All public functions are fire-and-forget safe: they return a boolean
result and never raise, so a Twilio outage can be caught by the caller.
"""
from __future__ import annotations

import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)
_VERIFY_BASE = "https://verify.twilio.com/v2/Services"


def is_configured(settings: Settings) -> bool:
    """Return True when all three Twilio Verify credentials are present."""
    return bool(
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_verify_service_sid
    )


async def send_otp(phone: str, settings: Settings) -> bool:
    """
    Ask Twilio to generate and send a 6-digit OTP via SMS.

    Returns True on success, False on any failure (never raises).
    """
    if not is_configured(settings):
        return False

    url = f"{_VERIFY_BASE}/{settings.twilio_verify_service_sid}/Verifications"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                url,
                data={"To": phone, "Channel": "sms"},
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            )
        if r.status_code >= 400:
            logger.error("Twilio send_otp error %s: %s", r.status_code, r.text[:300])
            return False
        return True
    except Exception as exc:
        logger.error("Twilio send_otp failed: %s", exc)
        return False


async def check_otp(phone: str, code: str, settings: Settings) -> bool:
    """
    Verify a 6-digit OTP code via Twilio Verify.

    Returns True if Twilio approves the code, False otherwise (never raises).
    """
    if not is_configured(settings):
        return False

    url = f"{_VERIFY_BASE}/{settings.twilio_verify_service_sid}/VerificationChecks"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                url,
                data={"To": phone, "Code": code},
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            )
        if r.status_code >= 400:
            logger.error("Twilio check_otp error %s: %s", r.status_code, r.text[:300])
            return False
        return r.json().get("status") == "approved"
    except Exception as exc:
        logger.error("Twilio check_otp failed: %s", exc)
        return False
