# Media Service (MS-5) — How It Works

## Architecture Overview

The media service uses a **two-process architecture** to separate HTTP request handling from heavy media processing:

```
┌─────────────────────┐       ┌──────────┐       ┌─────────────────────────┐
│   API Server        │       │  Redis   │       │   Worker Process(es)    │
│   (FastAPI/Uvicorn) │──────>│  Queue   │──────>│   (ARQ)                 │
│   Port 8005         │ LPUSH │          │ BRPOP │                         │
│                     │       │          │       │  - Image resize/compress │
│  - Upload URLs      │       │          │       │  - Video transcode poll  │
│  - Confirm upload   │       │          │       │  - S3 upload variants    │
│  - Serve files      │       │          │       │  - DB status update      │
│  - Playback info    │       │          │       │                         │
└─────────────────────┘       └──────────┘       └─────────────────────────┘
        │                                                │
        │  Own DB pool                      Own DB pool  │
        ▼                                                ▼
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL (platform_db)                  │
└─────────────────────────────────────────────────────────────┘
```

## Running the Service

You need **two terminals** (both from `services/media/`):

```bash
# Terminal 1 — API server (handles HTTP requests)
bash main.sh

# Terminal 2 — Worker (processes images/videos from Redis queue)
bash worker.sh
```

### Scaling Workers

Each worker process handles up to 20 concurrent jobs. For higher throughput, run multiple workers:

```bash
# Terminal 2
bash worker.sh

# Terminal 3
bash worker.sh

# Terminal 4
bash worker.sh
```

3 workers = 60 concurrent processing tasks. This handles ~4000 images in ~3.5 minutes.

## Upload Flow

### Step 1: Request Upload URL
```
POST /api/v1/media/upload
Authorization: Bearer <token>
{
  "asset_type": "IMAGE",           // IMAGE | VIDEO | PDF | SCORM
  "content_type": "image/png",
  "original_filename": "photo.png"
}

Response:
{
  "asset_id": "uuid",
  "upload_url": "https://s3.amazonaws.com/...",  // presigned PUT URL
  "s3_key": "uploads/image/<user_id>/<timestamp>_<random>.png",
  "expires_in": 900
}
```

### Step 2: Upload File Directly to S3
```
PUT <upload_url>
Content-Type: image/png
Body: <raw file bytes>
```

### Step 3: Confirm Upload
```
POST /api/v1/media/upload/confirm
Authorization: Bearer <token>
{
  "asset_id": "uuid"
}
```

This validates the file exists on S3, checks file size, and **enqueues a processing job to Redis**. The API returns immediately (~50ms).

## Image Processing (Worker)

When the worker picks up a `process_image` job:

1. Download original from S3
2. Pillow processing (in thread pool — CPU-bound):
   - Resize to multiple sizes (thumbnail 150x150, medium 600x600, large 1200x1200)
   - Compress and convert to WebP
3. Upload processed variants back to S3
4. Update DB: `transcode_status = COMPLETED`, store processed URLs

Processing time: ~2-5 seconds per image.

## Video Processing (Worker)

When the worker picks up a `process_video` job:

1. Submit AWS MediaConvert job (HLS: 720p + 1080p + 4K, plus MP4 + thumbnail)
2. Update DB: `transcode_status = PROCESSING`, store `mediaconvert_job_id`
3. Poll MediaConvert every 30 seconds until COMPLETE or ERROR
4. Update DB: `transcode_status = COMPLETED`, store HLS URL + thumbnail URL

Processing time: ~2-5 minutes depending on video length.

## Video Playback (Frontend)

### Immediate playback (no wait for transcoding)
The frontend plays the original MP4 via `/api/v1/media/serve/<s3_key>` immediately after upload. No waiting for MediaConvert.

### HLS upgrade (automatic)
The `VideoPlayer` component polls `GET /api/v1/media/playback/<asset_id>` every 30 seconds. When `transcode_status` becomes `COMPLETED`, it initializes HLS.js with the adaptive stream URL. The player auto-selects 720p/1080p/4K based on the user's bandwidth.

```
GET /api/v1/media/playback/<asset_id>   (public, no auth)

Response:
{
  "asset_id": "uuid",
  "transcode_status": "COMPLETED",      // PENDING | PROCESSING | COMPLETED | FAILED
  "hls_url": "/media/stream/processed/video/.../hls/master.m3u8",
  "thumbnail_url": "/media/serve/processed/video/.../thumbnail.jpg",
  "original_url": "/media/serve/uploads/video/.../original.mp4"
}
```

### Why `/media/stream/` exists (not just `/media/serve/`)
- `/media/serve/<key>` → 302 redirect to S3 presigned URL. Works for images and direct video playback.
- `/media/stream/<key>` → Proxies content directly (no redirect). Required for HLS because `.m3u8` playlists reference segments by relative paths — a redirect changes the base URL and breaks segment resolution.

## Key Endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /api/v1/media/upload` | Yes | Get presigned S3 upload URL |
| `POST /api/v1/media/upload/confirm` | Yes | Confirm upload, enqueue processing |
| `GET /api/v1/media/serve/<s3_key>` | No | 302 redirect to S3 (images, MP4) |
| `GET /api/v1/media/stream/<s3_key>` | No | Proxy content (HLS segments) |
| `GET /api/v1/media/playback/<asset_id>` | No | Video playback metadata |
| `GET /api/v1/media/assets` | Yes | List user's assets |
| `GET /api/v1/media/assets/<id>` | Yes | Get asset details |
| `DELETE /api/v1/media/assets/<id>` | Yes | Delete an asset |

## Job Queue Details (ARQ)

- **Library**: [ARQ](https://arq-docs.helpmanual.io/) — async Redis job queue for Python
- **Redis queue name**: `media:tasks`
- **Max concurrent jobs per worker**: 20
- **Max retries**: 3 (with exponential backoff)
- **Job timeout**: 30 minutes (for long video transcodes)
- **Result retention**: 1 hour

### Monitoring

Check Redis for queue status:
```bash
redis-cli

# Pending jobs
LLEN arq:media:tasks

# Active jobs (approximate)
KEYS arq:job:*
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIA_DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for job queue |
| `AWS_ACCESS_KEY_ID` | — | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | — | AWS credentials |
| `AWS_REGION` | `ap-south-1` | AWS region |
| `S3_BUCKET_MEDIA` | `docfliq-user-content-dev` | S3 bucket for uploads |
| `MEDIACONVERT_ENDPOINT` | — | MediaConvert API endpoint |
| `MEDIACONVERT_ROLE_ARN` | — | IAM role for MediaConvert |

## Capacity Planning

| Scenario | Workers | Concurrent Jobs | Throughput |
|----------|---------|-----------------|------------|
| Development | 1 | 20 | ~7 images/sec |
| Small prod | 2 | 40 | ~13 images/sec |
| 2000 users × 2 images | 3 | 60 | ~4000 images in ~3.5 min |
| High traffic | 5+ | 100+ | Linear scaling |

Workers are stateless — just run more instances for more throughput.
