"""
Brevo (Sendinblue) transactional email client — async httpx REST calls.

All send_* functions are fire-and-forget: they log on failure but never raise,
so a Brevo outage never breaks the primary user-facing flow.
Intended exclusively for use inside FastAPI BackgroundTasks.
"""
from __future__ import annotations

import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)
_BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _payload(to_email: str, to_name: str, subject: str, html: str, s: Settings) -> dict:
    return {
        "sender": {"email": s.brevo_from_email, "name": s.brevo_from_name},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html,
    }


async def _post(payload: dict, api_key: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                _BREVO_URL,
                json=payload,
                headers={"api-key": api_key, "Content-Type": "application/json"},
            )
        if r.status_code >= 400:
            logger.error("Brevo error %s: %s", r.status_code, r.text[:300])
    except httpx.HTTPError as exc:
        logger.error("Brevo request failed: %s", exc)


async def send_welcome(to_email: str, full_name: str, settings: Settings) -> None:
    if not settings.brevo_api_key:
        return
    await _post(
        _payload(
            to_email, full_name,
            "Welcome to DOCFLIQ!",
            f"<p>Hi {full_name},</p>"
            "<p>Welcome to DOCFLIQ! Upload your professional credentials to get verified "
            "and unlock full platform access.</p>",
            settings,
        ),
        settings.brevo_api_key,
    )


async def send_verification_submitted(
    to_email: str, full_name: str, settings: Settings
) -> None:
    if not settings.brevo_api_key:
        return
    await _post(
        _payload(
            to_email, full_name,
            "Your document is under review — DOCFLIQ",
            f"<p>Hi {full_name},</p>"
            "<p>We've received your verification document. It's now in our review queue "
            "and you'll hear back within 24 hours.</p>",
            settings,
        ),
        settings.brevo_api_key,
    )


async def send_verification_submitted_admin(
    admin_email: str,
    user_name: str,
    user_email: str,
    doc_type: str,
    settings: Settings,
) -> None:
    """Notify the admin team that a new verification document is awaiting review."""
    if not settings.brevo_api_key or not admin_email:
        return
    admin_panel_url = f"{settings.app_base_url}/admin/verification"
    await _post(
        {
            "sender": {"email": settings.brevo_from_email, "name": settings.brevo_from_name},
            "to": [{"email": admin_email, "name": "DOCFLIQ Admin"}],
            "subject": f"[Action Required] New verification document — {user_name}",
            "htmlContent": (
                "<p>A new verification document has been submitted and is awaiting review.</p>"
                "<table style='border-collapse:collapse;margin:16px 0'>"
                f"<tr><td style='padding:4px 12px 4px 0'><strong>User name:</strong></td>"
                f"<td>{user_name}</td></tr>"
                f"<tr><td style='padding:4px 12px 4px 0'><strong>User email:</strong></td>"
                f"<td>{user_email}</td></tr>"
                f"<tr><td style='padding:4px 12px 4px 0'><strong>Document type:</strong></td>"
                f"<td>{doc_type.replace('_', ' ').title()}</td></tr>"
                "</table>"
                f"<p style='margin-top:24px'>"
                f"<a href='{admin_panel_url}' "
                f"style='background:#2563eb;color:#fff;padding:12px 24px;border-radius:6px;"
                f"text-decoration:none;font-weight:bold'>Open Admin Review Queue →</a></p>"
                "<p style='color:#6b7280;font-size:13px;margin-top:32px'>"
                "This is an automated notification from DOCFLIQ Identity Service.</p>"
            ),
        },
        settings.brevo_api_key,
    )


async def send_verification_approved(
    to_email: str, full_name: str, settings: Settings
) -> None:
    if not settings.brevo_api_key:
        return
    await _post(
        _payload(
            to_email, full_name,
            "You're verified on DOCFLIQ!",
            f"<p>Hi {full_name},</p>"
            "<p>Congratulations! Your professional credentials have been verified. "
            "You now have full access to all DOCFLIQ content.</p>",
            settings,
        ),
        settings.brevo_api_key,
    )


async def send_password_reset_otp(
    to_email: str,
    full_name: str,
    otp_code: str,
    settings: Settings,
    reset_link: str = "",
) -> None:
    """
    Send the password reset email with both a 6-digit OTP code (15 min) and
    a clickable reset link (1 hour) as required by the MS-1 client spec.
    """
    if not settings.brevo_api_key:
        return
    link_section = (
        f"<p style='text-align:center;margin:32px 0'>"
        f"<a href='{reset_link}' "
        f"style='background:#2563eb;color:#fff;padding:14px 28px;border-radius:6px;"
        f"text-decoration:none;font-weight:bold'>Reset My Password</a></p>"
        f"<p>Or copy this link into your browser:</p>"
        f"<p style='word-break:break-all;color:#6b7280'>{reset_link}</p>"
        f"<p>The reset link expires in <strong>1 hour</strong>.</p>"
        if reset_link else ""
    )
    await _post(
        _payload(
            to_email, full_name,
            "Your DOCFLIQ password reset code",
            f"<p>Hi {full_name},</p>"
            f"<p>We received a request to reset your DOCFLIQ password. "
            f"You can reset it using either option below.</p>"
            f"<hr style='margin:24px 0'/>"
            f"<h3 style='margin:0 0 8px'>Option 1 — Enter the code manually</h3>"
            f"<p>Your reset code: <strong style='font-size:24px;letter-spacing:4px'>"
            f"{otp_code}</strong></p>"
            f"<p>This code expires in <strong>15 minutes</strong>.</p>"
            f"<hr style='margin:24px 0'/>"
            f"<h3 style='margin:0 0 8px'>Option 2 — Click the reset link</h3>"
            f"{link_section}"
            f"<p style='color:#6b7280;font-size:13px;margin-top:32px'>"
            f"If you did not request a password reset, you can safely ignore this email. "
            f"Your password will not change.</p>",
            settings,
        ),
        settings.brevo_api_key,
    )


async def send_email_verification(
    to_email: str, full_name: str, verification_url: str, settings: Settings
) -> None:
    if not settings.brevo_api_key:
        return
    await _post(
        _payload(
            to_email, full_name,
            "Verify your DOCFLIQ email address",
            f"<p>Hi {full_name},</p>"
            "<p>Welcome to DOCFLIQ! Please verify your email address by clicking the button below.</p>"
            f"<p style='text-align:center;margin:32px 0'>"
            f"<a href='{verification_url}' "
            f"style='background:#2563eb;color:#fff;padding:14px 28px;border-radius:6px;"
            f"text-decoration:none;font-weight:bold'>Verify Email Address</a></p>"
            "<p>Or copy and paste this link into your browser:</p>"
            f"<p style='word-break:break-all;color:#6b7280'>{verification_url}</p>"
            "<p>This link expires in <strong>24 hours</strong>. "
            "If you did not create a DOCFLIQ account, you can safely ignore this email.</p>",
            settings,
        ),
        settings.brevo_api_key,
    )


async def send_account_locked(
    to_email: str, full_name: str, settings: Settings
) -> None:
    if not settings.brevo_api_key:
        return
    await _post(
        _payload(
            to_email, full_name,
            "Security alert: Your DOCFLIQ account has been temporarily locked",
            f"<p>Hi {full_name},</p>"
            "<p>We detected <strong>5 failed login attempts</strong> on your DOCFLIQ account. "
            "As a security measure, your account has been <strong>temporarily locked for 30 minutes</strong>.</p>"
            "<p>If this was you, simply wait 30 minutes and try again.</p>"
            "<p>If you did not attempt to log in, we strongly recommend resetting your password "
            "immediately using the link below:</p>"
            "<p><a href='https://app.docfliq.com/auth/forgot-password'>Reset My Password</a></p>"
            "<p style='color:#6b7280;font-size:13px'>"
            "This is an automated security alert. Do not reply to this email.</p>",
            settings,
        ),
        settings.brevo_api_key,
    )


async def send_account_suspended(
    to_email: str, full_name: str, reason: str, settings: Settings
) -> None:
    if not settings.brevo_api_key:
        return
    await _post(
        _payload(
            to_email, full_name,
            "Your DOCFLIQ account has been suspended",
            f"<p>Hi {full_name},</p>"
            "<p>Your DOCFLIQ account has been <strong>suspended</strong> by our moderation team.</p>"
            f"<p><strong>Reason:</strong> {reason}</p>"
            "<p>If you believe this is a mistake, please contact support at "
            "<a href='mailto:support@docfliq.com'>support@docfliq.com</a>.</p>"
            "<p style='color:#6b7280;font-size:13px'>"
            "This is an automated notification from DOCFLIQ.</p>",
            settings,
        ),
        settings.brevo_api_key,
    )


async def send_verification_rejected(
    to_email: str, full_name: str, reason: str, settings: Settings
) -> None:
    if not settings.brevo_api_key:
        return
    await _post(
        _payload(
            to_email, full_name,
            "Action required: DOCFLIQ verification update",
            f"<p>Hi {full_name},</p>"
            f"<p>We were unable to verify your document for the following reason:</p>"
            f"<blockquote>{reason}</blockquote>"
            "<p>Please log in and re-upload a valid document to try again.</p>",
            settings,
        ),
        settings.brevo_api_key,
    )
