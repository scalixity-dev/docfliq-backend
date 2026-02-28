# Docfliq Identity (MS-1)

Auth, profile, verification, and social graph microservice.

## Run

```bash
./run.sh
# or
uv sync && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

API docs: `http://localhost:8001/docs`

## Environment Variables

Loads `../../.env` (backend root). See backend `.env.example` for full list.

| Variable | Required | Description |
|---|---|---|
| `IDENTITY_DATABASE_URL` | ✅ | `postgresql+asyncpg://user:pass@host/db` |
| `JWT_SECRET` | ✅ | Random 32+ char secret for JWT signing |
| `REDIS_URL` | ✅ | `redis://localhost:6379/0` — rate limiting + email verification + login lockout |
| `APP_BASE_URL` | ⬜ | Base URL of the frontend app (default: `http://localhost:3000`) — used to build email verification links |
| `CORS_ORIGINS` | ✅ | Comma-separated allowed origins |
| `BREVO_API_KEY` | ✅ | Brevo transactional email API key |
| `BREVO_FROM_EMAIL` | ⬜ | Sender address (default: `noreply@docfliq.com`) |
| `BREVO_FROM_NAME` | ⬜ | Sender display name (default: `DOCFLIQ`) |
| `AWS_ACCESS_KEY_ID` | ✅ | IAM key with `s3:GetObject` + `s3:PutObject` on the bucket |
| `AWS_SECRET_ACCESS_KEY` | ✅ | Corresponding secret |
| `AWS_REGION` | ⬜ | Default: `us-east-1` |
| `S3_BUCKET` | ⬜ | Default: `docfliq-user-content-prod` |
| `S3_PRESIGNED_EXPIRY_SECONDS` | ⬜ | PUT URL TTL (default: `900`) |
| `ACCESS_TOKEN_EXPIRE_SECONDS` | ⬜ | Default: `900` (15 min) |
| `REFRESH_TOKEN_EXPIRE_SECONDS` | ⬜ | Default: `604800` (7 days) |

---

## Token Lifetimes

| Token | Lifetime |
|---|---|
| Access token (JWT) | 15 minutes |
| Refresh token (opaque) | 7 days |
| OTP code | 5 minutes |
| Password reset OTP (code) | 15 minutes |
| Password reset link token (Redis) | 1 hour |
| Email verification token (Redis) | 24 hours |
| Presigned PUT URL (upload) | 15 minutes |
| Presigned GET URL (admin view) | 30 minutes |

---

## Base URL

All routes are prefixed with `/api/v1`.

---

## Auth Domain

### POST `/api/v1/auth/register`

Register a new account with email + password. A verification email with a 24-hour link is sent immediately after registration as a background task.

**Rate limit:** 3 requests / hour per IP

**Request:**
```json
{
  "email": "doctor@example.com",
  "password": "Str0ngPass!",
  "full_name": "Dr. Jane Smith",
  "role": "doctor_specialist",
  "phone_number": "+919876543210",
  "specialty": "Cardiology",
  "sub_specialty": "Interventional",
  "years_of_experience": 10,
  "medical_license_number": "MH-12345",
  "hospital_name": "Apollo Hospital Mumbai"
}
```

All role-specific fields are optional at signup — they can be completed later via `PATCH /users/me`. The profile response includes `profile_complete` and `missing_required_fields` to guide users.

| Field | Type | Required | Role | Notes |
|---|---|---|---|---|
| `email` | string | ✅ | All | Valid email |
| `password` | string | ✅ | All | 8–128 chars |
| `full_name` | string | ✅ | All | 2–150 chars |
| `role` | UserRole | ✅ | All | See enum below |
| `phone_number` | string | ⬜ | All | E.164 format, e.g. `+919876543210` |
| `specialty` | string | ⬜ | Doctor, Nurse | Max 100 chars |
| `sub_specialty` | string | ⬜ | Doctor Specialist | Max 100 chars |
| `years_of_experience` | integer | ⬜ | Doctor, Nurse | 0–80 |
| `medical_license_number` | string | ⬜ | Doctor | Max 100 chars |
| `hospital_name` | string | ⬜ | Doctor, Nurse | Max 200 chars |
| `certification` | string | ⬜ | Nurse | Specialty certification / area credential. Max 200 chars |
| `university` | string | ⬜ | Student | Max 200 chars |
| `graduation_year` | integer | ⬜ | Student | 1980–2060 |
| `student_id` | string | ⬜ | Student | University-issued ID. Max 100 chars |
| `pharmacist_license_number` | string | ⬜ | Pharmacist | Max 100 chars |
| `pharmacy_name` | string | ⬜ | Pharmacist | Max 200 chars |

**UserRole values:** `doctor_specialist` · `doctor_gp` · `nurse` · `student` · `pharmacist` · `admin`

**Required fields per role (for profile completion + verification eligibility):**

| Role | Required to complete profile |
|---|---|
| `doctor_specialist` | `specialty`, `hospital_name`, `medical_license_number` |
| `doctor_gp` | `specialty`, `hospital_name`, `medical_license_number` |
| `nurse` | `specialty`, `hospital_name`, `certification` |
| `student` | `university`, `graduation_year`, `student_id` |
| `pharmacist` | `pharmacist_license_number`, `pharmacy_name` |

**Response `201 Created`:**
```json
{
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "doctor@example.com",
    "full_name": "Dr. Jane Smith",
    "role": "doctor_specialist",
    "phone_number": "+919876543210",
    "specialty": "Cardiology",
    "verification_status": "unverified",
    "content_creation_mode": false,
    "is_active": true,
    "created_at": "2024-01-15T10:30:00Z"
  },
  "tokens": {
    "access_token": "<JWT>",
    "refresh_token": "<opaque>",
    "token_type": "bearer",
    "expires_in": 900
  }
}
```

**Errors:** `409` email already registered · `422` validation · `429` rate limit

---

### POST `/api/v1/auth/login`

Login with email + password.

**Rate limit:** 5 requests / 15 minutes per IP

**Request:**
```json
{
  "email": "doctor@example.com",
  "password": "Str0ngPass!"
}
```

**Response `200 OK`:**
```json
{
  "access_token": "<JWT>",
  "refresh_token": "<opaque>",
  "token_type": "bearer",
  "expires_in": 900
}
```

**Errors:** `401` invalid credentials · `403` account temporarily locked (5 failed attempts, 30-minute lock) · `429` rate limit (IP-level)

> **Login lockout:** After 5 consecutive failed login attempts for the same email address, the account is locked for 30 minutes and a security alert email is sent. The 5-attempt window resets 15 minutes after the first failed attempt. Successful login clears the counter immediately.

---

### POST `/api/v1/auth/refresh`

Rotate refresh token and get a new access + refresh pair.

**Request:**
```json
{ "refresh_token": "<opaque>" }
```

**Response `200 OK`:** Same shape as `/auth/login`

**Errors:** `401` token expired, invalid, session not found, or account banned/suspended/inactive

---

### POST `/api/v1/auth/logout`

Invalidate a single session (device logout).

**Request:**
```json
{ "refresh_token": "<opaque>" }
```

**Response `204 No Content`**

---

### POST `/api/v1/auth/otp/request`

Request a 6-digit OTP via SMS (mobile login).

When **Twilio Verify** is configured (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`), Twilio generates and delivers the OTP via SMS. When Twilio is **not** configured (development), the OTP is generated locally and stored in Redis/PostgreSQL but no SMS is sent.

**Rate limit:** 3 requests / 10 minutes per IP

**Request:**
```json
{ "phone_number": "+919876543210" }
```

**Response `200 OK`:**
```json
{ "message": "OTP sent successfully." }
```

**Errors:** `502` SMS delivery temporarily unavailable (Twilio down)

---

### POST `/api/v1/auth/password-reset/request`

Request a password reset. Sends a **single email** containing two options:
- A **6-digit OTP code** (enter manually in-app, expires in 15 minutes)
- A **clickable reset link** (expires in 1 hour — client spec requirement)

**Rate limit:** 3 requests / hour per IP

**Request:**
```json
{ "email": "doctor@example.com" }
```

**Response `200 OK`** (always — even if the email is not registered):
```json
{ "message": "If an account exists for this email, a reset code has been sent." }
```

**Errors:** `429` rate limit

---

### POST `/api/v1/auth/password-reset/confirm`

Reset password using the **6-digit OTP code** from the email. Invalidates all active sessions on success.

**Request:**
```json
{
  "email": "doctor@example.com",
  "otp_code": "482913",
  "new_password": "NewStr0ng!Pass"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `email` | string | ✅ | Must match the address used in `/request` |
| `otp_code` | string | ✅ | Exactly 6 digits |
| `new_password` | string | ✅ | 8–128 chars |

**Response `200 OK`:**
```json
{ "message": "Password reset successfully. Please log in with your new password." }
```

**Errors:** `401` invalid or expired OTP · `401` too many failed attempts

---

### POST `/api/v1/auth/password-reset/confirm-link`

Reset password using the **URL token from the reset link** in the email. Token expires in 1 hour and is single-use. Invalidates all active sessions on success.

**Request:**
```json
{
  "token": "<url-safe token from reset link>",
  "new_password": "NewStr0ng!Pass"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `token` | string | ✅ | URL-safe token from the `?token=` query param in the reset link |
| `new_password` | string | ✅ | 8–128 chars |

**Response `200 OK`:**
```json
{ "message": "Password reset successfully. Please log in with your new password." }
```

**Errors:** `401` token not found, already used, or expired

---

### GET `/api/v1/auth/email/verify`

Verify an email address using the token from the verification email. Marks `email_verified = true` on the user record. The token is a one-time Redis key that expires after 24 hours.

**Query params:**

| Param | Required | Notes |
|---|---|---|
| `token` | ✅ | URL-safe token from the verification link |

**Response `200 OK`:**
```json
{ "message": "Email verified successfully." }
```

**Errors:** `401` token not found, already used, or expired

---

### POST `/api/v1/auth/email/resend-verification`

Resend the email verification link. Generates a fresh 24-hour token (previous token is invalidated) and sends a new email. Requires an active access token.

**Auth:** `Authorization: Bearer <access_token>` required

**Response `200 OK`:**
```json
{ "message": "Verification email sent. Please check your inbox." }
```

**Errors:** `401` invalid/expired access token

---

### POST `/api/v1/auth/otp/verify`

Verify OTP and get tokens. Creates account on first use (requires `full_name` + `role`). When Twilio Verify is configured, the code is verified by Twilio's API; otherwise it is checked against local Redis/PostgreSQL storage.

**Request:**
```json
{
  "phone_number": "+919876543210",
  "otp_code": "123456",
  "full_name": "Dr. Jane Smith",
  "role": "doctor_specialist"
}
```

| Field | Required | Notes |
|---|---|---|
| `phone_number` | ✅ | E.164 format |
| `otp_code` | ✅ | Exactly 6 digits |
| `full_name` | ⬜ | Required for first-time OTP registration |
| `role` | ⬜ | Required for first-time OTP registration |

**Response `200 OK`:** Same shape as `/auth/login`

**Errors:** `401` invalid or expired OTP

---

## Profile Domain

All routes require `Authorization: Bearer <access_token>`.

### GET `/api/v1/users/me`

Get own full profile.

**Response `200 OK`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "doctor@example.com",
  "full_name": "Dr. Jane Smith",
  "role": "doctor_specialist",
  "specialty": "Cardiology",
  "sub_specialty": "Interventional",
  "years_of_experience": 10,
  "location_city": "Mumbai",
  "location_state": "Maharashtra",
  "location_country": "India",
  "profile_image_url": null,
  "bio": "Experienced interventional cardiologist.",
  "interests": ["cardiology", "heart failure"],
  "verification_status": "verified",
  "content_creation_mode": true,
  "email_verified": true,
  "medical_license_number": "MH-12345",
  "hospital_name": "Apollo Hospital Mumbai",
  "certification": null,
  "university": null,
  "graduation_year": null,
  "student_id": null,
  "pharmacist_license_number": null,
  "pharmacy_name": null,
  "created_at": "2024-01-15T10:30:00Z",
  "capabilities": {
    "can_create_courses": true,
    "can_be_speaker": true,
    "can_post_community": true,
    "has_full_content_access": true,
    "student_restricted": false
  },
  "profile_complete": true,
  "missing_required_fields": []
}
```

> **`capabilities`** — computed from `role` + `verification_status`. Enforcement happens in downstream content/webinar services that read the JWT `role` claim. Identity exposes these flags so the frontend can show/hide UI elements without extra API calls.
>
> **`profile_complete`** — `true` when all role-required fields are filled. **`missing_required_fields`** — list of field names the user still needs to provide for their role (see required fields table under `/auth/register`). Both are `false`/`[]` after registration; users fill these in via `PATCH /users/me`.

---

### PATCH `/api/v1/users/me`

Partial update of own profile. Only provided fields are written.

**Request** (all fields optional — provide only what you want to update):
```json
{
  "full_name": "Dr. Jane M. Smith",
  "specialty": "Cardiology",
  "sub_specialty": "Interventional",
  "years_of_experience": 11,
  "location_city": "Pune",
  "location_state": "Maharashtra",
  "location_country": "India",
  "bio": "Updated bio.",
  "interests": ["cardiology", "echocardiography"],
  "medical_license_number": "MH-12345",
  "hospital_name": "Fortis Hospital Pune"
}
```

| Field | Type | Constraint | Role |
|---|---|---|---|
| `full_name` | string | Max 150 chars | All |
| `specialty` | string | Max 100 chars | Doctor, Nurse |
| `sub_specialty` | string | Max 100 chars | Doctor Specialist |
| `years_of_experience` | integer | 0–80 | Doctor, Nurse |
| `location_city` | string | Max 100 chars | All |
| `location_state` | string | Max 100 chars | All |
| `location_country` | string | Max 50 chars | All |
| `bio` | string | — | All |
| `interests` | string[] | — | All |
| `medical_license_number` | string | Max 100 chars | Doctor |
| `hospital_name` | string | Max 200 chars | Doctor, Nurse |
| `certification` | string | Max 200 chars | Nurse |
| `university` | string | Max 200 chars | Student |
| `graduation_year` | integer | 1980–2060 | Student |
| `student_id` | string | Max 100 chars | Student |
| `pharmacist_license_number` | string | Max 100 chars | Pharmacist |
| `pharmacy_name` | string | Max 200 chars | Pharmacist |

**Response `200 OK`:** Same shape as `GET /users/me`

---

### GET `/api/v1/users/{user_id}`

Get any user's public profile by UUID.

**Response `200 OK`:** Same shape as `GET /users/me`

**Errors:** `404` user not found or has blocked you (block status is not disclosed)

---

## Verification Domain — User Routes

All routes require `Authorization: Bearer <access_token>`.

### Verification State Machine

```
UNVERIFIED ──submit──► PENDING ──approve──► VERIFIED
REJECTED   ──submit──► PENDING
PENDING    ──reject───► REJECTED
VERIFIED   ──submit──► 409 (blocked — already verified)
VERIFIED   ──suspend──► SUSPENDED  (admin only — all sessions invalidated)
SUSPENDED  ──reinstate─► VERIFIED  (admin only)
```

`content_creation_mode` becomes `true` upon approval.

---

### POST `/api/v1/users/me/verify/upload`

Request a presigned S3 PUT URL to upload a verification document. Client must PUT the file directly to `upload_url` within 15 minutes, then call `/confirm`.

**Request:**
```json
{
  "document_type": "medical_license",
  "content_type": "application/pdf"
}
```

| Field | Type | Required | Values |
|---|---|---|---|
| `document_type` | DocumentType | ✅ | `medical_license` · `id_card` · `degree` |
| `content_type` | string | ⬜ | `image/jpeg` · `image/png` · `application/pdf` (default) |

**Response `200 OK`:**
```json
{
  "upload_url": "https://s3.amazonaws.com/docfliq-user-content-prod/verifications/...",
  "document_key": "verifications/<user_id>/<uuid>.pdf",
  "expires_in": 900
}
```

**Errors:** `502` AWS presign failed

---

### POST `/api/v1/users/me/verify/confirm`

Confirm S3 upload complete and submit for admin review. User status → `PENDING`. Confirmation email sent via Brevo.

**Request:**
```json
{
  "document_key": "verifications/<user_id>/<uuid>.pdf",
  "document_type": "medical_license"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `document_key` | string | ✅ | Key returned by `/upload` |
| `document_type` | DocumentType | ✅ | Must match uploaded file |

**Response `201 Created`:**
```json
{
  "verification_id": "660f9500-...",
  "status": "pending",
  "message": "Your document has been submitted for review."
}
```

**Errors:** `400` document key not found in S3 · `409` account is already verified · `413` file exceeds 10 MB

---

## Verification Domain — Admin Routes

All routes require `Authorization: Bearer <access_token>` for a user with role `admin`.

### GET `/api/v1/admin/verification/queue`

Role-priority ordered list of `PENDING` verification documents (Doctors and Pharmacists first, then other roles), then FIFO within each priority tier.

**Query params:**

| Param | Default | Range |
|---|---|---|
| `page` | `1` | ≥ 1 |
| `size` | `20` | 1–100 |

**Response `200 OK`:**
```json
{
  "items": [
    {
      "id": "660f9500-...",
      "user_id": "550e8400-...",
      "user_name": "Dr. Jane Smith",
      "user_email": "doctor@example.com",
      "document_type": "medical_license",
      "status": "pending",
      "created_at": "2024-01-15T11:00:00Z"
    }
  ],
  "total": 42,
  "page": 1,
  "size": 20
}
```

**Errors:** `403` not an admin

---

### GET `/api/v1/admin/verification/{doc_id}/document`

Get a 30-minute presigned GET URL to view the uploaded document in-browser.

**Path param:** `doc_id` — UUID

**Response `200 OK`:**
```json
{
  "view_url": "https://s3.amazonaws.com/...",
  "expires_in": 1800,
  "document_type": "medical_license"
}
```

**Errors:** `403` not an admin · `404` document not found

---

### PATCH `/api/v1/admin/verification/{doc_id}/review`

Approve or reject a verification document.

| Action | Effect |
|---|---|
| `APPROVE` | `verification_status` → `VERIFIED`, `content_creation_mode = true`. Approval email sent. Idempotent guard: 409 if already approved. |
| `REJECT` | `verification_status` → `REJECTED` (user may re-upload). Rejection email with reason sent. |

**Path param:** `doc_id` — UUID

**Request:**
```json
{
  "action": "APPROVE",
  "notes": "Document looks valid."
}
```
```json
{
  "action": "REJECT",
  "notes": "License number is not visible. Please re-upload a clearer image."
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `action` | string | ✅ | `APPROVE` or `REJECT` |
| `notes` | string | ✅ on REJECT | Max 1000 chars |

**Response `200 OK`:**
```json
{
  "id": "660f9500-...",
  "status": "approved",
  "reviewed_at": "2024-01-15T14:00:00Z"
}
```

**Errors:** `403` not an admin · `404` document not found · `409` already approved

---

### PATCH `/api/v1/admin/verification/users/{user_id}/suspend`

Suspend a verified user. Sets `verification_status → SUSPENDED`, records the reason in `ban_reason`, and invalidates **all active sessions** (user is immediately logged out on every device). A suspension notification email is sent via Brevo.

**Path param:** `user_id` — UUID

**Request:**
```json
{ "reason": "Fraudulent medical licence detected." }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `reason` | string | ✅ | 1–500 chars — communicated to the user via email |

**Response `200 OK`:**
```json
{
  "id": "550e8400-...",
  "verification_status": "suspended"
}
```

**Errors:** `403` not an admin · `404` user not found · `409` user is already suspended

---

### PATCH `/api/v1/admin/verification/users/{user_id}/reinstate`

Reinstate a suspended user back to `VERIFIED`. Clears `ban_reason`. No email is sent automatically.

**Path param:** `user_id` — UUID

**Response `200 OK`:**
```json
{
  "id": "550e8400-...",
  "verification_status": "verified"
}
```

**Errors:** `403` not an admin · `404` user not found · `409` user is not currently suspended

---

## Social Graph Domain

All routes require `Authorization: Bearer <access_token>`.

### Follow / Unfollow

#### POST `/api/v1/users/{user_id}/follow`

Follow a user.

**Rate limit:** 50 requests / hour per IP

**Response `200 OK`:**
```json
{ "message": "Followed successfully." }
```

**Errors:** `409` already following · `409` target is blocked · `422` cannot follow self · `422` follow limit reached (5,000)

---

#### DELETE `/api/v1/users/{user_id}/follow`

Unfollow a user.

**Response `204 No Content`**

**Errors:** `404` not following

---

### Block / Unblock

#### POST `/api/v1/users/{user_id}/block`

Block a user. Also removes follow edges in both directions.

**Response `200 OK`:**
```json
{ "message": "User blocked." }
```

**Errors:** `409` already blocked · `422` cannot block self

---

#### DELETE `/api/v1/users/{user_id}/block`

Unblock a user.

**Response `204 No Content`**

**Errors:** `404` not blocked

---

### Mute / Unmute

#### POST `/api/v1/users/{user_id}/mute`

Mute a user (hides their content from your feed; independent of follow/block).

**Response `200 OK`:**
```json
{ "message": "User muted." }
```

**Errors:** `409` already muted · `422` cannot mute self

---

#### DELETE `/api/v1/users/{user_id}/mute`

Unmute a user.

**Response `204 No Content`**

**Errors:** `404` not muted

---

### Report

#### POST `/api/v1/users/{user_id}/report`

Submit a report about a user or their content.

**Request:**
```json
{
  "target_type": "user",
  "target_id": "550e8400-e29b-41d4-a716-446655440000",
  "reason": "Spam or misleading content."
}
```

| Field | Type | Required | Values |
|---|---|---|---|
| `target_type` | ReportTargetType | ✅ | `user` · `post` · `comment` · `webinar` |
| `target_id` | UUID | ✅ | The target's UUID |
| `reason` | string | ✅ | 1–255 chars |

**Response `201 Created`:**
```json
{
  "id": "660f9500-...",
  "status": "open",
  "created_at": "2024-01-15T12:00:00Z"
}
```

---

### My Lists (paginated)

All list endpoints accept `?page=1&size=20` (size max 100).

#### GET `/api/v1/users/me/following`

Users I follow.

**Response `200 OK`:**
```json
{
  "items": [
    {
      "id": "<follow_id>",
      "user": {
        "id": "...",
        "full_name": "Dr. Jane Smith",
        "role": "doctor_specialist",
        "specialty": "Cardiology",
        "profile_image_url": null,
        "verification_status": "verified"
      },
      "created_at": "2024-01-15T10:30:00Z",
      "is_followed_by_me": true
    }
  ],
  "total": 42,
  "page": 1,
  "size": 20
}
```

---

#### GET `/api/v1/users/me/followers`

Users who follow me. Same shape as `/me/following`.

---

#### GET `/api/v1/users/me/blocked`

Users I have blocked.

**Response `200 OK`:**
```json
{
  "items": [
    {
      "id": "<block_id>",
      "user": { ... },
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20
}
```

---

#### GET `/api/v1/users/me/muted`

Users I have muted. Same shape as `/me/blocked`.

---

### Another User's Lists

#### GET `/api/v1/users/{user_id}/following`

View another user's following list.

**Errors:** `404` user not found or has blocked you

---

#### GET `/api/v1/users/{user_id}/followers`

View another user's followers list.

**Errors:** `404` user not found or has blocked you

---

## Social Graph — Admin Routes

All routes require `Authorization: Bearer <access_token>` for a user with role `admin`.

### GET `/api/v1/admin/social/reports`

List all reports (FIFO order — oldest first).

**Query params:**

| Param | Default | Values |
|---|---|---|
| `status` | none (all) | `open` · `reviewed` · `actioned` · `dismissed` |
| `page` | `1` | ≥ 1 |
| `size` | `20` | 1–100 |

**Response `200 OK`:**
```json
{
  "items": [
    {
      "id": "660f9500-...",
      "reporter_id": "550e8400-...",
      "target_type": "user",
      "target_id": "770a1600-...",
      "reason": "Spam",
      "status": "open",
      "reviewed_by": null,
      "action_taken": null,
      "created_at": "2024-01-15T12:00:00Z"
    }
  ],
  "total": 15,
  "page": 1,
  "size": 20
}
```

---

### PATCH `/api/v1/admin/social/reports/{report_id}/review`

Handle a report.

**Request:**
```json
{
  "status": "actioned",
  "action_taken": "User warned and post removed."
}
```

| Field | Type | Required | Values |
|---|---|---|---|
| `status` | string | ✅ | `reviewed` · `actioned` · `dismissed` |
| `action_taken` | string | ⬜ | Max 100 chars |

**Response `200 OK`:** Full `AdminReportItem` (same shape as list item)

**Errors:** `403` not admin · `404` report not found

---

## Rate Limits Summary

| Endpoint | Limit |
|---|---|
| `POST /auth/register` | 3 / hour per IP |
| `POST /auth/login` | 5 / 15 minutes per IP |
| `POST /auth/otp/request` | 3 / 10 minutes per IP |
| `POST /auth/password-reset/request` | 3 / hour per IP |
| `POST /users/{user_id}/follow` | 50 / hour per IP |

Rate-limited responses return `429 Too Many Requests` with a `Retry-After` header.

---

## Email Notifications (Brevo)

| Trigger | Recipient |
|---|---|
| Successful registration | New user — welcome email + email verification link (24h) |
| Password reset requested | User — 6-digit OTP code (expires 15 min) |
| 5 consecutive failed logins | User — security alert + account temporarily locked (30 min) |
| Document submitted (`/confirm`) | User — submission confirmation |
| Admin approves document | User — verified, can now create content |
| Admin rejects document | User — rejection reason included |
| Admin suspends user | User — suspension notification including reason |

Email dispatch is non-blocking (`BackgroundTasks`). Failures are logged but never break the API response.

---

## Global Error Shape

```json
{ "detail": "Human-readable error message" }
```

Validation errors (`422`) return the standard Pydantic error list under `detail`.

---

## Phase 2 — Not Yet Implemented

The following features are specified in the MS-1 spec but are pending a future implementation phase. Stubs, constants, or enum values may already exist; endpoints do not.

| Feature | Notes |
|---|---|
| ~~**Password reset**~~ | ✅ Implemented — `POST /auth/password-reset/request` + `/confirm` (migration 003) |
| ~~**Email verification link**~~ | ✅ Implemented — 24h token stored in Redis, sent via Brevo on registration. `GET /auth/email/verify?token=` + `POST /auth/email/resend-verification`. Flag stored in `users.email_verified` (migration 004). |
| **Institutional SSO** (SAML 2.0 / OIDC) | Requires external IdP integration (e.g. Azure AD, Okta). No code exists yet. |
| ~~**Per-account login lockout**~~ | ✅ Implemented — 5 failed attempts (15-min window) → 30-min account lock stored in Redis + security alert email via Brevo. |
| ~~**Twilio SMS dispatch**~~ | ✅ Implemented — Twilio Verify V2 sends OTP via SMS. Async httpx calls to Twilio REST API. When Twilio credentials are absent (dev mode), falls back to local Redis/PostgreSQL OTP storage with no SMS sent. Env vars: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`. |
| **SNS / SQS event emission** | No domain events (`user.registered`, `user.verified`, `user.followed`, `user.profile_updated`, `user.suspended`) are emitted yet. |
| **Follow suggestions** | Pre-computed by Celery every 6 hours (noted as a TODO in `social_graph/service.py`). |
| **Redis debounce for follow events** | 3-second debounce to prevent notification spam from rapid follow/unfollow cycles (noted as a TODO in `social_graph/service.py`). |
| **Nightly Celery cleanup** | Background task to purge deleted-user IDs that may linger in follower/following lists after soft-deletes. |
| **Profile image upload** | `profile_image_url` column exists on the `users` table and is returned in API responses. No upload endpoint exists yet (will mirror the verification presigned-URL flow). |
