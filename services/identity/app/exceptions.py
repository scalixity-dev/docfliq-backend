"""
Identity service — domain-specific HTTP exceptions.

All exceptions use preset status codes and detail messages so that callers
never need to specify these at the call site.  The global error_envelope_middleware
in shared catches these and wraps them in the standard error envelope.
"""
from fastapi import HTTPException, status


# ── Authentication ────────────────────────────────────────────────────────────

class InvalidCredentials(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )


class TokenExpired(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        )


class TokenInvalid(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid.",
        )


class SessionNotFound(HTTPException):
    """Raised when the refresh token does not match any active session."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found or has expired. Please log in again.",
        )


# ── Registration / conflict ───────────────────────────────────────────────────

class UserAlreadyExists(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )


class PhoneAlreadyExists(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this phone number already exists.",
        )


# ── Account state ─────────────────────────────────────────────────────────────

class UserNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )


class UserInactive(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )


class UserBanned(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been banned.",
        )


class UserSuspended(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been suspended.",
        )


class UserAlreadySuspended(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user is already suspended.",
        )


class UserNotSuspended(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user is not currently suspended.",
        )


# ── OTP ───────────────────────────────────────────────────────────────────────

class OTPRateLimitExceeded(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Please wait before trying again.",
        )


class InvalidOTP(HTTPException):
    def __init__(self, attempts_remaining: int) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid OTP code. {attempts_remaining} attempt(s) remaining.",
        )


class OTPExpired(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail="OTP has expired. Please request a new code.",
        )


class OTPExhausted(HTTPException):
    """All verify attempts used up — user must request a new OTP."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Too many invalid attempts. Please request a new OTP.",
        )


class SMSDeliveryFailed(HTTPException):
    """Twilio (or other SMS provider) failed to deliver the OTP."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SMS delivery is temporarily unavailable. Please try again shortly.",
        )


class AccountLocked(HTTPException):
    """Raised when the account is temporarily locked after too many failed logins."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your account has been temporarily locked after too many failed login "
                "attempts. Please try again in 30 minutes or check your email for instructions."
            ),
        )


# ── Verification ──────────────────────────────────────────────────────────────

class VerificationDocNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification document not found.",
        )


class VerificationAlreadyApproved(HTTPException):
    """Idempotent guard — admin tried to approve/reject an already-approved doc."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document has already been approved.",
        )


class CannotResubmitVerification(HTTPException):
    """User is already VERIFIED — re-upload blocked."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your account is already verified. Contact support if you need to update credentials.",
        )


class VerificationDocNotPending(HTTPException):
    """Admin tried to approve/reject a doc that is not in PENDING state."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document is not in PENDING state and cannot be reviewed.",
        )


# ── S3 ────────────────────────────────────────────────────────────────────────

class S3PresignError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not generate document upload URL. Please try again.",
        )


class S3ObjectNotFound(HTTPException):
    """Raised when the document_key passed to /confirm does not exist in S3."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The document_key does not match any uploaded file. "
                "Please upload the file to the presigned URL before confirming."
            ),
        )


class FileTooLarge(HTTPException):
    """Raised when the uploaded file exceeds the maximum allowed size (10 MB)."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The uploaded file exceeds the maximum allowed size of 10 MB. Please upload a smaller file.",
        )


# ── Social graph ───────────────────────────────────────────────────────────────

class CannotFollowSelf(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="You cannot follow yourself.")


class AlreadyFollowing(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail="You are already following this user.")


class NotFollowing(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="You are not following this user.")


class FollowLimitExceeded(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You have reached the maximum following limit (5,000).",
        )


class CannotBlockSelf(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="You cannot block yourself.")


class AlreadyBlocked(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail="You have already blocked this user.")


class NotBlocked(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="You have not blocked this user.")


class CannotMuteSelf(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="You cannot mute yourself.")


class AlreadyMuted(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail="You have already muted this user.")


class NotMuted(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="You have not muted this user.")


class UserHiddenByBlock(HTTPException):
    """Target user has blocked the current user — return 404 to avoid leaking block status."""

    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")


class ReportNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
