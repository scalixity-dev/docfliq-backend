import enum

# ── Token lifetimes (per MS-1 spec) ──────────────────────────────────────────
ACCESS_TOKEN_EXPIRE_SECONDS: int = 900          # 15 minutes
REFRESH_TOKEN_EXPIRE_SECONDS: int = 86_400 * 7  # 7 days
OTP_EXPIRE_SECONDS: int = 300                    # 5 minutes
EMAIL_VERIFY_EXPIRE_SECONDS: int = 86_400        # 24 hours
PASSWORD_RESET_LINK_EXPIRE_SECONDS: int = 3_600  # 1 hour (spec requirement)

# ── Max concurrent sessions per user (per MS-1 spec) ─────────────────────────
MAX_SESSIONS_PER_USER: int = 5


# ── User professional role (selected during signup) ───────────────────────────
class UserRole(str, enum.Enum):
    DOCTOR_SPECIALIST = "doctor_specialist"
    DOCTOR_GP = "doctor_gp"
    NURSE = "nurse"
    STUDENT = "student"
    PHARMACIST = "pharmacist"
    ADMIN = "admin"


# ── Verification lifecycle state machine (per MS-1 spec) ─────────────────────
class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"   # New user — no document uploaded
    PENDING = "pending"          # Document uploaded, awaiting admin review
    VERIFIED = "verified"        # Admin approved
    REJECTED = "rejected"        # Admin rejected (user can re-upload)
    SUSPENDED = "suspended"      # Admin suspended (all access revoked)


# ── Verification document type ────────────────────────────────────────────────
class DocumentType(str, enum.Enum):
    MEDICAL_LICENSE = "medical_license"
    ID_CARD = "id_card"
    DEGREE = "degree"


# ── Verification document review status ──────────────────────────────────────
class VerificationDocStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"  # Old rejected doc superseded by a re-upload


# ── OTP purpose ───────────────────────────────────────────────────────────────
class OTPPurpose(str, enum.Enum):
    LOGIN = "login"
    TWO_FA = "2fa"
    PASSWORD_RESET = "password_reset"
