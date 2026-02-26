# AWS Setup Guide — Docfliq Media Service (MS-5)

Minimal S3-only setup. No Lambda, MediaConvert, EventBridge, or CloudFront needed.

Images are processed in-service (Pillow). Videos are stored as-is (original MP4).

---

## 1. Create the S3 Bucket

Go to **S3 → Create bucket**:

| Setting | Value |
|---------|-------|
| Bucket name | `docfliq-user-content-dev` |
| Region | `ap-south-1` (Mumbai) |
| Block all public access | **ON** (checked) |
| Bucket Versioning | Disabled |
| Default encryption | SSE-S3 |

### CORS Configuration

Go to **Permissions → CORS** and paste:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT", "GET", "HEAD"],
    "AllowedOrigins": [
      "http://localhost:3000",
      "https://your-production-domain.com"
    ],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 600
  }
]
```

### (Optional) Lifecycle Rule

Go to **Management → Lifecycle rules → Create rule**:
- Rule name: `abort-incomplete-uploads`
- Scope: Apply to all objects
- Action: **Delete incomplete multipart uploads** after **1 day**

---

## 2. Create IAM User

Go to **IAM → Users → Create user**:

| Setting | Value |
|---------|-------|
| User name | `docfliq-media-service` |
| Access type | **Programmatic access** (access key) |

### Attach Inline Policy

Create an inline policy named `docfliq-s3-media-access`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3MediaAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:HeadObject"
      ],
      "Resource": "arn:aws:s3:::docfliq-user-content-dev/*"
    }
  ]
}
```

### Create Access Key

Go to **Security credentials → Create access key** → select **Application running outside AWS**.

Save the `Access Key ID` and `Secret Access Key`.

---

## 3. Environment Variables

Add to your `.env` file (backend root):

```env
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-south-1
S3_BUCKET_MEDIA=docfliq-user-content-dev
```

That's it. The media service reads these via `pydantic-settings`.

---

## 4. Verify

```bash
# Install dependencies
cd services/media
uv pip install -e .

# Start the service
./run.sh   # or: uvicorn app.main:app --port 8005

# Test upload flow
# 1. POST /api/v1/media/upload   → get presigned PUT URL
# 2. PUT <presigned_url>         → upload file directly to S3
# 3. POST /api/v1/media/upload/confirm → triggers background processing (images)
# 4. GET /api/v1/media/assets/{id}     → poll until transcode_status = COMPLETED
```

### What happens per asset type

| Type | Processing | Result |
|------|-----------|--------|
| **IMAGE** | Pillow (background task): thumbnail 150x150, medium 600x600, large 1200x1200, all WebP | `processed_url` = large, `thumbnail_url` = thumbnail |
| **VIDEO** | None — original MP4 stored as-is | `processed_url` = original URL, `hls_url` = null |
| **PDF** | None | `transcode_status` = COMPLETED immediately |
| **SCORM** | None | `transcode_status` = COMPLETED immediately |
