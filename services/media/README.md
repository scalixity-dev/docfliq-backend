# Docfliq Media Processing Service (MS-5)

Event-driven media processing microservice. Provides a FastAPI REST API for managing media assets (upload, status tracking, secure URLs) and AWS Lambda functions for actual media processing (video transcoding, image resizing, virus scanning).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend / Other Services                   │
│                                                                  │
│  1. POST /media/upload    → get presigned S3 PUT URL            │
│  2. PUT  <presigned_url>  → upload file directly to S3          │
│  3. POST /media/upload/confirm → confirm upload + validate      │
│                                                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────▼───────────────┐
         │   FastAPI API (port 8005)      │
         │   Media Asset Management       │
         │   • Upload URLs                │
         │   • Asset CRUD                 │
         │   • Signed download URLs       │
         │   • Status tracking            │
         └───────────────┬───────────────┘
                         │
         ┌───────────────▼───────────────┐
         │          AWS S3                │
         │   docfliq-user-content-dev     │
         │                               │
         │   uploads/video/{user}/...    │
         │   uploads/image/{user}/...    │
         │   processed/video/{user}/...  │
         │   processed/image/{user}/...  │
         └──┬────────────┬──────────┬───┘
            │            │          │
    ┌───────▼──┐  ┌──────▼───┐  ┌──▼──────────┐
    │ Lambda:  │  │ Lambda:  │  │ Lambda:     │
    │ Virus    │  │ Video    │  │ Image       │
    │ Scan     │  │ Transcode│  │ Processing  │
    │ (ClamAV) │  │ (Media-  │  │ (Pillow)    │
    │          │  │ Convert) │  │             │
    └──────────┘  └──────────┘  └─────────────┘
         │            │               │
         │     ┌──────▼───────┐       │
         │     │  AWS Media-  │       │
         │     │  Convert     │       │
         │     │  HLS + MP4   │       │
         │     └──────────────┘       │
         │                            │
         └─── callback POST ──────────┘
              to /api/v1/internal/media/callback/*
```

## Directory Structure

```
services/media/
├── app/                           # FastAPI application
│   ├── main.py                    # App factory, middleware, routes
│   ├── config.py                  # Settings (env vars)
│   ├── database.py                # SQLAlchemy async sessions
│   ├── redis_client.py            # Redis singleton
│   ├── rate_limit.py              # slowapi limiter
│   ├── exceptions.py              # HTTP exceptions
│   ├── s3.py                      # S3 presigned URLs
│   └── asset/                     # Media asset domain
│       ├── constants.py           # Enums, sizes, presets
│       ├── models.py              # MediaAsset ORM model
│       ├── schemas.py             # Pydantic V2 schemas
│       ├── service.py             # Pure business logic
│       ├── controller.py          # Request orchestration
│       ├── router.py              # HTTP routes
│       └── dependencies.py        # Auth guards
│
├── lambdas/                       # Lambda function code (zip & deploy)
│   ├── video_transcode/           # Video → HLS + MP4
│   │   ├── handler.py             # S3 trigger entry point
│   │   ├── mediaconvert_job.py    # MediaConvert job builder
│   │   ├── callback.py            # EventBridge completion handler
│   │   └── requirements.txt
│   ├── image_process/             # Image resize + WebP conversion
│   │   ├── handler.py             # S3 trigger entry point
│   │   ├── processor.py           # Pillow image processing
│   │   └── requirements.txt
│   └── virus_scan/                # ClamAV malware scanning
│       ├── handler.py             # S3 trigger entry point
│       └── requirements.txt
│
├── handlers/                      # Legacy stubs (kept for compatibility)
├── tests/
├── pyproject.toml                 # uv dependencies
├── run.sh                         # Auto-setup + start
├── .python-version                # Python 3.12
└── README.md
```

## Quick Start (Local API)

```bash
# From services/media/
chmod +x run.sh
./run.sh

# API available at http://localhost:8005
# Docs at http://localhost:8005/docs
```

## Prerequisites

### 1. Database Setup

Create the `media_db` database on your PostgreSQL instance:

```sql
CREATE DATABASE media_db;
```

### 2. Environment Variables

Add to `docfliq-backend/.env`:

```env
# Already added:
MEDIA_DATABASE_URL=postgresql+asyncpg://postgres:<password>@<host>:5432/media_db
```

### 3. Run Migrations

```bash
cd migrations/media
MEDIA_DATABASE_URL=postgresql+asyncpg://postgres:<password>@<host>:5432/media_db \
  ../../services/media/.venv/bin/alembic upgrade head
```

## API Endpoints

### User-facing (require Bearer token)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/media/upload` | Get presigned S3 PUT URL for upload |
| `POST` | `/api/v1/media/upload/confirm` | Confirm file uploaded to S3 |
| `GET` | `/api/v1/media/assets` | List my media assets (paginated) |
| `GET` | `/api/v1/media/assets/{id}` | Get single asset details |
| `DELETE` | `/api/v1/media/assets/{id}` | Delete an asset |
| `GET` | `/api/v1/media/assets/{id}/url` | Get signed download URL |

### Internal (Lambda callbacks)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/internal/media/callback/transcode` | Video transcode result |
| `POST` | `/api/v1/internal/media/callback/image` | Image processing result |

## Upload Flow

1. **Client** → `POST /media/upload` with `{asset_type, content_type, original_filename}`
2. **API** → returns `{asset_id, upload_url, s3_key, expires_in}`
3. **Client** → `PUT upload_url` with the file binary (direct to S3)
4. **Client** → `POST /media/upload/confirm` with `{asset_id}`
5. **API** → validates file exists in S3, checks size, marks for processing
6. **S3 event** → triggers virus scan Lambda
7. If clean: triggers video/image processing Lambda
8. **Lambda** → calls callback endpoint to update asset status

## AWS Lambda Deployment

### Video Transcoding Lambda

```bash
cd lambdas/video_transcode
pip install -r requirements.txt -t package/
cp handler.py mediaconvert_job.py package/
cd package && zip -r ../video-transcode.zip . && cd ..

# Deploy via AWS CLI
aws lambda create-function \
  --function-name docfliq-video-transcode \
  --runtime python3.12 \
  --handler handler.handler \
  --role arn:aws:iam::<ACCOUNT>:role/docfliq-lambda-media \
  --zip-file fileb://video-transcode.zip \
  --timeout 60 \
  --memory-size 256 \
  --environment Variables='{
    MEDIACONVERT_ENDPOINT=<endpoint>,
    MEDIACONVERT_ROLE_ARN=arn:aws:iam::<ACCOUNT>:role/docfliq-mediaconvert,
    OUTPUT_BUCKET=docfliq-user-content-dev,
    CALLBACK_URL=https://api.docfliq.com/api/v1/internal/media/callback/transcode
  }'
```

### MediaConvert Completion Handler

```bash
cd lambdas/video_transcode
pip install -r requirements.txt -t cb_package/
cp callback.py cb_package/handler.py
cd cb_package && zip -r ../transcode-callback.zip . && cd ..

# Deploy + create EventBridge rule
aws lambda create-function \
  --function-name docfliq-transcode-callback \
  --runtime python3.12 \
  --handler handler.handler \
  --role arn:aws:iam::<ACCOUNT>:role/docfliq-lambda-media \
  --zip-file fileb://transcode-callback.zip \
  --timeout 30 \
  --environment Variables='{
    CALLBACK_URL=https://api.docfliq.com/api/v1/internal/media/callback/transcode,
    CLOUDFRONT_DOMAIN=cdn.docfliq.com
  }'

# EventBridge rule for MediaConvert job status changes
aws events put-rule \
  --name docfliq-mediaconvert-status \
  --event-pattern '{
    "source": ["aws.mediaconvert"],
    "detail-type": ["MediaConvert Job State Change"],
    "detail": {"status": ["COMPLETE", "ERROR"]}
  }'

aws events put-targets \
  --rule docfliq-mediaconvert-status \
  --targets "Id"="1","Arn"="arn:aws:lambda:<region>:<account>:function:docfliq-transcode-callback"
```

### Image Processing Lambda

```bash
cd lambdas/image_process
pip install -r requirements.txt -t package/
cp handler.py processor.py package/
cd package && zip -r ../image-process.zip . && cd ..

aws lambda create-function \
  --function-name docfliq-image-process \
  --runtime python3.12 \
  --handler handler.handler \
  --role arn:aws:iam::<ACCOUNT>:role/docfliq-lambda-media \
  --zip-file fileb://image-process.zip \
  --timeout 120 \
  --memory-size 512 \
  --environment Variables='{
    OUTPUT_BUCKET=docfliq-user-content-dev,
    CALLBACK_URL=https://api.docfliq.com/api/v1/internal/media/callback/image
  }'
```

### Virus Scan Lambda

```bash
# Requires ClamAV Lambda Layer (build or use open-source layer)
cd lambdas/virus_scan
pip install -r requirements.txt -t package/
cp handler.py package/
cd package && zip -r ../virus-scan.zip . && cd ..

aws lambda create-function \
  --function-name docfliq-virus-scan \
  --runtime python3.12 \
  --handler handler.handler \
  --role arn:aws:iam::<ACCOUNT>:role/docfliq-lambda-media \
  --zip-file fileb://virus-scan.zip \
  --timeout 300 \
  --memory-size 1024 \
  --layers arn:aws:lambda:<region>:<account>:layer:clamav:1
```

### S3 Event Triggers

Configure S3 to trigger Lambdas on file upload:

```bash
# Virus scan for all uploads
aws s3api put-bucket-notification-configuration \
  --bucket docfliq-user-content-dev \
  --notification-configuration '{
    "LambdaFunctionConfigurations": [
      {
        "LambdaFunctionArn": "arn:aws:lambda:<region>:<account>:function:docfliq-virus-scan",
        "Events": ["s3:ObjectCreated:*"],
        "Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": "uploads/"}]}}
      },
      {
        "LambdaFunctionArn": "arn:aws:lambda:<region>:<account>:function:docfliq-video-transcode",
        "Events": ["s3:ObjectCreated:*"],
        "Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": "uploads/video/"}]}}
      },
      {
        "LambdaFunctionArn": "arn:aws:lambda:<region>:<account>:function:docfliq-image-process",
        "Events": ["s3:ObjectCreated:*"],
        "Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": "uploads/image/"}]}}
      }
    ]
  }'
```

## AWS IAM Roles Required

### Lambda Execution Role (`docfliq-lambda-media`)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
        "s3:PutObjectTagging", "s3:GetObjectTagging"
      ],
      "Resource": "arn:aws:s3:::docfliq-user-content-dev/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "mediaconvert:CreateJob", "mediaconvert:GetJob",
        "mediaconvert:DescribeEndpoints"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
      "Resource": "arn:aws:sqs:*:*:docfliq-*"
    }
  ]
}
```

### MediaConvert Role (`docfliq-mediaconvert`)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::docfliq-user-content-dev/*"
    }
  ]
}
```

## CloudFront Signed URLs (Production)

When ready for production, configure CloudFront:

1. **Create CloudFront distribution** pointing to the S3 bucket
2. **Create CloudFront key pair** (or trusted key group)
3. **Set environment variables:**

```env
CLOUDFRONT_DOMAIN=cdn.docfliq.com
CLOUDFRONT_KEY_PAIR_ID=K2XXXXXXXXXXXX
CLOUDFRONT_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n...
```

4. Add CloudFront signed URL generation to `app/s3.py`

### Signed URL Expiry by Content Type

| Content Type | URL Type | Expiry |
|-------------|----------|--------|
| Free public content | Standard CloudFront | No expiry |
| Paid course videos | CloudFront signed URL | 4 hours |
| Paid course PDFs | CloudFront signed URL | 2 hours |
| Webinar VOD | CloudFront signed URL | 8 hours |
| User upload (PUT) | S3 presigned URL | 15 minutes |
| Verification docs | S3 presigned GET | 30 minutes |

## S3 Bucket Configuration

### Lifecycle Rules

```bash
# Clean up incomplete multipart uploads after 24 hours
aws s3api put-bucket-lifecycle-configuration \
  --bucket docfliq-user-content-dev \
  --lifecycle-configuration '{
    "Rules": [
      {
        "ID": "abort-incomplete-uploads",
        "Status": "Enabled",
        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
        "Filter": {"Prefix": "uploads/"}
      }
    ]
  }'
```

### CORS Configuration

Already configured for the bucket. If needed:

```bash
aws s3api put-bucket-cors \
  --bucket docfliq-user-content-dev \
  --cors-configuration '{
    "CORSRules": [{
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["PUT", "GET"],
      "AllowedOrigins": ["http://localhost:3000", "https://docfliq.com"],
      "MaxAgeSeconds": 3600
    }]
  }'
```

## Integration with Other Services

The Media Service integrates with:

- **MS-1 (Identity)**: JWT token validation via shared auth module
- **MS-2 (Content)**: Content service stores `asset_id` references for post/course media
- **MS-3 (Course)**: Course service references `asset_id` for course videos and PDFs
- **MS-6 (Webinar)**: Webinar recordings sent via SQS for transcoding

## Monitoring

- **CloudWatch Logs**: All Lambda functions log to CloudWatch
- **MediaConvert Console**: Monitor transcoding jobs
- **S3 Metrics**: Track upload counts and sizes
- **Health Check**: `GET /health` returns `{"status": "ok", "service": "media"}`
