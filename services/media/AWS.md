# AWS Setup Guide — Docfliq Media Processing Service (MS-5)

This guide walks you through every AWS resource you need to create, step by step.
Follow the sections in order.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Create the S3 Bucket](#2-create-the-s3-bucket)
3. [Create IAM Roles](#3-create-iam-roles)
4. [Set Up AWS MediaConvert](#4-set-up-aws-mediaconvert)
5. [Deploy Lambda Functions](#5-deploy-lambda-functions)
6. [Connect S3 Events to Lambda](#6-connect-s3-events-to-lambda)
7. [Set Up EventBridge for MediaConvert Callbacks](#7-set-up-eventbridge-for-mediaconvert-callbacks)
8. [Set Up CloudFront (Production)](#8-set-up-cloudfront-production)
9. [Update Environment Variables](#9-update-environment-variables)
10. [Test the Full Flow](#10-test-the-full-flow)
11. [Monitoring & Troubleshooting](#11-monitoring--troubleshooting)

---

## 1. Prerequisites

Before you start, make sure you have:

- [ ] AWS CLI installed and configured (`aws configure`)
- [ ] Your AWS Account ID (find it in top-right corner of AWS Console)
- [ ] Region decided: **ap-south-1** (Mumbai) — same as your RDS
- [ ] Python 3.12 installed locally (for packaging Lambda functions)

```bash
# Verify AWS CLI is working
aws sts get-caller-identity

# Note your Account ID from the output — you'll need it everywhere below
# Example output: "Account": "123456789012"
```

**Replace these placeholders throughout this guide:**
- `<ACCOUNT_ID>` → your AWS account ID (e.g., `123456789012`)
- `<REGION>` → `ap-south-1`

---

## 2. Create the S3 Bucket

You already have `docfliq-user-content-dev`. Make sure it has the right configuration.

### 2a. Verify the bucket exists

```bash
aws s3 ls s3://docfliq-user-content-dev/ --region ap-south-1
```

### 2b. Create folder structure

```bash
# These are virtual folders — S3 creates them automatically on upload,
# but creating them now helps visualize the structure
aws s3api put-object --bucket docfliq-user-content-dev --key uploads/video/
aws s3api put-object --bucket docfliq-user-content-dev --key uploads/image/
aws s3api put-object --bucket docfliq-user-content-dev --key uploads/pdf/
aws s3api put-object --bucket docfliq-user-content-dev --key uploads/scorm/
aws s3api put-object --bucket docfliq-user-content-dev --key processed/video/
aws s3api put-object --bucket docfliq-user-content-dev --key processed/image/
```

### 2c. Set CORS (already done, but verify)

```bash
aws s3api get-bucket-cors --bucket docfliq-user-content-dev
```

If empty, set it:

```bash
aws s3api put-bucket-cors --bucket docfliq-user-content-dev --cors-configuration '{
  "CORSRules": [
    {
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["PUT", "GET", "HEAD"],
      "AllowedOrigins": ["http://localhost:3000", "https://docfliq.com"],
      "MaxAgeSeconds": 3600,
      "ExposeHeaders": ["ETag"]
    }
  ]
}'
```

### 2d. Set lifecycle rule (clean incomplete uploads)

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket docfliq-user-content-dev \
  --lifecycle-configuration '{
    "Rules": [
      {
        "ID": "abort-incomplete-multipart-uploads",
        "Status": "Enabled",
        "Filter": { "Prefix": "uploads/" },
        "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 1 }
      }
    ]
  }'
```

### 2e. Enable versioning (optional but recommended)

```bash
aws s3api put-bucket-versioning \
  --bucket docfliq-user-content-dev \
  --versioning-configuration Status=Enabled
```

---

## 3. Create IAM Roles

You need **2 IAM roles**:
1. **Lambda execution role** — lets Lambda functions access S3, MediaConvert, CloudWatch
2. **MediaConvert role** — lets MediaConvert read/write to S3

### 3a. Create the Lambda execution role

**Step 1: Create the trust policy file**

Save this as `/tmp/lambda-trust-policy.json`:

```bash
cat > /tmp/lambda-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
```

**Step 2: Create the role**

```bash
aws iam create-role \
  --role-name docfliq-lambda-media \
  --assume-role-policy-document file:///tmp/lambda-trust-policy.json \
  --description "Docfliq media processing Lambda execution role"
```

**Step 3: Save the role ARN from the output** — you'll need it later:
```
arn:aws:iam::<ACCOUNT_ID>:role/docfliq-lambda-media
```

**Step 4: Attach the permissions policy**

Save this as `/tmp/lambda-media-policy.json`:

```bash
cat > /tmp/lambda-media-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:PutObjectTagging",
        "s3:GetObjectTagging",
        "s3:HeadObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::docfliq-user-content-dev",
        "arn:aws:s3:::docfliq-user-content-dev/*"
      ]
    },
    {
      "Sid": "MediaConvertAccess",
      "Effect": "Allow",
      "Action": [
        "mediaconvert:CreateJob",
        "mediaconvert:GetJob",
        "mediaconvert:ListJobs",
        "mediaconvert:DescribeEndpoints"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Sid": "PassRoleToMediaConvert",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::*:role/docfliq-mediaconvert"
    }
  ]
}
EOF
```

```bash
aws iam put-role-policy \
  --role-name docfliq-lambda-media \
  --policy-name docfliq-lambda-media-policy \
  --policy-document file:///tmp/lambda-media-policy.json
```

### 3b. Create the MediaConvert role

**Step 1: Create trust policy**

```bash
cat > /tmp/mediaconvert-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "mediaconvert.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
```

**Step 2: Create the role**

```bash
aws iam create-role \
  --role-name docfliq-mediaconvert \
  --assume-role-policy-document file:///tmp/mediaconvert-trust-policy.json \
  --description "Docfliq MediaConvert S3 access role"
```

**Step 3: Attach S3 permissions**

```bash
cat > /tmp/mediaconvert-s3-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::docfliq-user-content-dev/*"
    }
  ]
}
EOF
```

```bash
aws iam put-role-policy \
  --role-name docfliq-mediaconvert \
  --policy-name docfliq-mediaconvert-s3 \
  --policy-document file:///tmp/mediaconvert-s3-policy.json
```

---

## 4. Set Up AWS MediaConvert

### 4a. Get your MediaConvert endpoint

Every AWS account has a unique MediaConvert endpoint per region. Get yours:

```bash
aws mediaconvert describe-endpoints --region ap-south-1
```

Output:
```json
{
  "Endpoints": [
    {
      "Url": "https://abc123def.mediaconvert.ap-south-1.amazonaws.com"
    }
  ]
}
```

**Save this URL** — you'll set it as `MEDIACONVERT_ENDPOINT`.

### 4b. Create a MediaConvert queue (optional)

The default queue works fine. If you want a dedicated queue:

```bash
aws mediaconvert create-queue \
  --name docfliq-media-queue \
  --region ap-south-1 \
  --endpoint-url <YOUR_MEDIACONVERT_ENDPOINT>
```

Save the queue ARN from the output.

---

## 5. Deploy Lambda Functions

### 5a. Video Transcoding Lambda

```bash
cd /home/bsc/WORK/Scalixity/DOCFLIQ/docfliq-backend/services/media/lambdas/video_transcode

# Install dependencies into a package directory
pip install -r requirements.txt --target package/ --platform manylinux2014_x86_64 --only-binary=:all:

# Copy handler code
cp handler.py package/
cp mediaconvert_job.py package/

# Create the zip
cd package
zip -r ../video-transcode.zip .
cd ..

# Deploy
aws lambda create-function \
  --function-name docfliq-video-transcode \
  --runtime python3.12 \
  --handler handler.handler \
  --role arn:aws:iam::<ACCOUNT_ID>:role/docfliq-lambda-media \
  --zip-file fileb://video-transcode.zip \
  --timeout 60 \
  --memory-size 256 \
  --region ap-south-1 \
  --environment "Variables={
    MEDIACONVERT_ENDPOINT=<YOUR_MEDIACONVERT_ENDPOINT>,
    MEDIACONVERT_ROLE_ARN=arn:aws:iam::<ACCOUNT_ID>:role/docfliq-mediaconvert,
    OUTPUT_BUCKET=docfliq-user-content-dev,
    CALLBACK_URL=http://<YOUR_SERVER_IP>:8005/api/v1/internal/media/callback/transcode
  }"

# Clean up
rm -rf package video-transcode.zip
```

### 5b. MediaConvert Callback Lambda

This separate Lambda handles MediaConvert job completion events:

```bash
cd /home/bsc/WORK/Scalixity/DOCFLIQ/docfliq-backend/services/media/lambdas/video_transcode

pip install -r requirements.txt --target cb_package/ --platform manylinux2014_x86_64 --only-binary=:all:

# For the callback, the entry point is callback.py renamed to handler.py
cp callback.py cb_package/handler.py

cd cb_package
zip -r ../transcode-callback.zip .
cd ..

aws lambda create-function \
  --function-name docfliq-transcode-callback \
  --runtime python3.12 \
  --handler handler.handler \
  --role arn:aws:iam::<ACCOUNT_ID>:role/docfliq-lambda-media \
  --zip-file fileb://transcode-callback.zip \
  --timeout 30 \
  --memory-size 128 \
  --region ap-south-1 \
  --environment "Variables={
    CALLBACK_URL=http://<YOUR_SERVER_IP>:8005/api/v1/internal/media/callback/transcode,
    OUTPUT_BUCKET=docfliq-user-content-dev,
    CLOUDFRONT_DOMAIN=
  }"

rm -rf cb_package transcode-callback.zip
```

### 5c. Image Processing Lambda

```bash
cd /home/bsc/WORK/Scalixity/DOCFLIQ/docfliq-backend/services/media/lambdas/image_process

pip install -r requirements.txt --target package/ --platform manylinux2014_x86_64 --only-binary=:all:

cp handler.py package/
cp processor.py package/

cd package
zip -r ../image-process.zip .
cd ..

aws lambda create-function \
  --function-name docfliq-image-process \
  --runtime python3.12 \
  --handler handler.handler \
  --role arn:aws:iam::<ACCOUNT_ID>:role/docfliq-lambda-media \
  --zip-file fileb://image-process.zip \
  --timeout 120 \
  --memory-size 512 \
  --region ap-south-1 \
  --environment "Variables={
    OUTPUT_BUCKET=docfliq-user-content-dev,
    CALLBACK_URL=http://<YOUR_SERVER_IP>:8005/api/v1/internal/media/callback/image
  }"

rm -rf package image-process.zip
```

### 5d. Virus Scan Lambda (Optional — do this later)

ClamAV requires a Lambda Layer with the ClamAV binary + virus definitions (~400 MB).
Skip this for now and add it when going to production.

```bash
# When ready:
cd /home/bsc/WORK/Scalixity/DOCFLIQ/docfliq-backend/services/media/lambdas/virus_scan

pip install -r requirements.txt --target package/ --platform manylinux2014_x86_64 --only-binary=:all:
cp handler.py package/

cd package
zip -r ../virus-scan.zip .
cd ..

# You need a ClamAV Lambda Layer first.
# Option 1: Use an open-source one from https://github.com/awslabs/cdk-serverless-clamscan
# Option 2: Build your own from https://github.com/truework/lambda-clamav-layer

aws lambda create-function \
  --function-name docfliq-virus-scan \
  --runtime python3.12 \
  --handler handler.handler \
  --role arn:aws:iam::<ACCOUNT_ID>:role/docfliq-lambda-media \
  --zip-file fileb://virus-scan.zip \
  --timeout 300 \
  --memory-size 1024 \
  --region ap-south-1 \
  --layers arn:aws:lambda:ap-south-1:<ACCOUNT_ID>:layer:clamav:1

rm -rf package virus-scan.zip
```

---

## 6. Connect S3 Events to Lambda

When a file is uploaded to S3, it needs to trigger the right Lambda function.

### 6a. Grant S3 permission to invoke Lambda

You must do this **before** setting up S3 notifications, or it will fail:

```bash
# Permission for video transcoding
aws lambda add-permission \
  --function-name docfliq-video-transcode \
  --statement-id s3-invoke-video \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::docfliq-user-content-dev \
  --source-account <ACCOUNT_ID> \
  --region ap-south-1

# Permission for image processing
aws lambda add-permission \
  --function-name docfliq-image-process \
  --statement-id s3-invoke-image \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::docfliq-user-content-dev \
  --source-account <ACCOUNT_ID> \
  --region ap-south-1
```

### 6b. Configure S3 event notifications

```bash
cat > /tmp/s3-notifications.json << 'EOF'
{
  "LambdaFunctionConfigurations": [
    {
      "Id": "video-upload-trigger",
      "LambdaFunctionArn": "arn:aws:lambda:ap-south-1:<ACCOUNT_ID>:function:docfliq-video-transcode",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            { "Name": "prefix", "Value": "uploads/video/" }
          ]
        }
      }
    },
    {
      "Id": "image-upload-trigger",
      "LambdaFunctionArn": "arn:aws:lambda:ap-south-1:<ACCOUNT_ID>:function:docfliq-image-process",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            { "Name": "prefix", "Value": "uploads/image/" }
          ]
        }
      }
    }
  ]
}
EOF
```

**IMPORTANT:** Replace `<ACCOUNT_ID>` in the file before running:

```bash
# Replace placeholder with your actual account ID
sed -i 's/<ACCOUNT_ID>/123456789012/g' /tmp/s3-notifications.json

# Apply the notification configuration
aws s3api put-bucket-notification-configuration \
  --bucket docfliq-user-content-dev \
  --notification-configuration file:///tmp/s3-notifications.json
```

### 6c. Verify notifications are set

```bash
aws s3api get-bucket-notification-configuration \
  --bucket docfliq-user-content-dev
```

---

## 7. Set Up EventBridge for MediaConvert Callbacks

When MediaConvert finishes transcoding a video, it emits an event.
EventBridge catches this and triggers our callback Lambda.

### 7a. Create the EventBridge rule

```bash
aws events put-rule \
  --name docfliq-mediaconvert-job-status \
  --event-pattern '{
    "source": ["aws.mediaconvert"],
    "detail-type": ["MediaConvert Job State Change"],
    "detail": {
      "status": ["COMPLETE", "ERROR"]
    }
  }' \
  --description "Trigger callback Lambda when MediaConvert jobs complete or fail" \
  --region ap-south-1
```

### 7b. Grant EventBridge permission to invoke the callback Lambda

```bash
aws lambda add-permission \
  --function-name docfliq-transcode-callback \
  --statement-id eventbridge-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:ap-south-1:<ACCOUNT_ID>:rule/docfliq-mediaconvert-job-status \
  --region ap-south-1
```

### 7c. Add the Lambda as a target

```bash
aws events put-targets \
  --rule docfliq-mediaconvert-job-status \
  --targets "Id=transcode-callback,Arn=arn:aws:lambda:ap-south-1:<ACCOUNT_ID>:function:docfliq-transcode-callback" \
  --region ap-south-1
```

### 7d. Verify

```bash
aws events list-targets-by-rule \
  --rule docfliq-mediaconvert-job-status \
  --region ap-south-1
```

---

## 8. Set Up CloudFront (Production)

Skip this for development. Do this when you're ready for production.

### 8a. Create a CloudFront key group

```bash
# Generate a key pair for signed URLs
openssl genrsa -out /tmp/cloudfront-private-key.pem 2048
openssl rsa -pubout -in /tmp/cloudfront-private-key.pem -out /tmp/cloudfront-public-key.pem

# Upload the public key to CloudFront
aws cloudfront create-public-key \
  --public-key-config '{
    "CallerReference": "docfliq-media-key-2026",
    "Name": "docfliq-media-signing-key",
    "EncodedKey": "'"$(cat /tmp/cloudfront-public-key.pem)"'"
  }'
```

Save the public key ID from the output (e.g., `K2JXXXXXXXXXX`).

```bash
# Create a key group
aws cloudfront create-key-group \
  --key-group-config '{
    "Name": "docfliq-media-key-group",
    "Items": ["<PUBLIC_KEY_ID>"]
  }'
```

### 8b. Create CloudFront distribution

Do this in the AWS Console — it's much easier than CLI:

1. Go to **CloudFront** → **Create Distribution**
2. **Origin domain**: `docfliq-user-content-dev.s3.ap-south-1.amazonaws.com`
3. **Origin access**: Origin access control (OAC) — create new
4. **Viewer protocol policy**: Redirect HTTP to HTTPS
5. **Allowed HTTP methods**: GET, HEAD
6. **Cache policy**: CachingOptimized
7. **Restrict viewer access**: Yes → Trusted key groups → select your key group
8. **Price class**: Use only North America, Europe, Asia (or All)
9. **Alternate domain**: `cdn.docfliq.com` (if you have the domain)
10. Click **Create Distribution**

Save the distribution domain (e.g., `d1234abcdef.cloudfront.net`).

### 8c. Update S3 bucket policy for OAC

CloudFront will provide you with the bucket policy statement. Copy it and add it:

```bash
aws s3api put-bucket-policy \
  --bucket docfliq-user-content-dev \
  --policy '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "AllowCloudFrontServicePrincipal",
        "Effect": "Allow",
        "Principal": {
          "Service": "cloudfront.amazonaws.com"
        },
        "Action": "s3:GetObject",
        "Resource": "arn:aws:s3:::docfliq-user-content-dev/*",
        "Condition": {
          "StringEquals": {
            "AWS:SourceArn": "arn:aws:cloudfront::<ACCOUNT_ID>:distribution/<DISTRIBUTION_ID>"
          }
        }
      }
    ]
  }'
```

---

## 9. Update Environment Variables

After completing the AWS setup, update your `.env` file:

```env
# ── MediaConvert ─────────────────────────────────────────────
# Get this from: aws mediaconvert describe-endpoints
MEDIACONVERT_ENDPOINT=https://abc123def.mediaconvert.ap-south-1.amazonaws.com

# Get this from: aws iam get-role --role-name docfliq-mediaconvert
MEDIACONVERT_ROLE_ARN=arn:aws:iam::<ACCOUNT_ID>:role/docfliq-mediaconvert

# Only if you created a custom queue (otherwise leave empty)
MEDIACONVERT_QUEUE_ARN=

# Same as S3_BUCKET_MEDIA
MEDIACONVERT_OUTPUT_BUCKET=docfliq-user-content-dev

# ── CloudFront (production only) ─────────────────────────────
# Leave empty for development — presigned S3 URLs will be used instead
CLOUDFRONT_DOMAIN=
CLOUDFRONT_KEY_PAIR_ID=
CLOUDFRONT_PRIVATE_KEY=
```

---

## 10. Test the Full Flow

### 10a. Test video upload flow

```bash
# 1. Start the media service
cd /home/bsc/WORK/Scalixity/DOCFLIQ/docfliq-backend/services/media
./run.sh

# 2. Get an access token (login via identity service)
TOKEN="your-jwt-access-token-here"

# 3. Request upload URL
curl -X POST http://localhost:8005/api/v1/media/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "VIDEO",
    "content_type": "video/mp4",
    "original_filename": "test-video.mp4"
  }'

# Response: { "asset_id": "...", "upload_url": "https://s3...", "s3_key": "...", "expires_in": 900 }

# 4. Upload the file to S3 using the presigned URL
curl -X PUT "<upload_url_from_step_3>" \
  -H "Content-Type: video/mp4" \
  --data-binary @/path/to/test-video.mp4

# 5. Confirm the upload
curl -X POST http://localhost:8005/api/v1/media/upload/confirm \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "asset_id": "<asset_id_from_step_3>" }'

# 6. Check asset status (should transition from PENDING → PROCESSING → COMPLETED)
curl http://localhost:8005/api/v1/media/assets/<asset_id> \
  -H "Authorization: Bearer $TOKEN"

# 7. Get signed download URL
curl http://localhost:8005/api/v1/media/assets/<asset_id>/url \
  -H "Authorization: Bearer $TOKEN"
```

### 10b. Test image upload flow

```bash
curl -X POST http://localhost:8005/api/v1/media/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "IMAGE",
    "content_type": "image/jpeg",
    "original_filename": "profile-photo.jpg"
  }'

# Upload + confirm same as video flow
```

### 10c. Verify Lambda execution

```bash
# Check Lambda logs
aws logs tail /aws/lambda/docfliq-video-transcode --follow --region ap-south-1
aws logs tail /aws/lambda/docfliq-image-process --follow --region ap-south-1

# Check MediaConvert jobs
aws mediaconvert list-jobs \
  --region ap-south-1 \
  --endpoint-url <YOUR_MEDIACONVERT_ENDPOINT> \
  --order DESCENDING \
  --max-results 5
```

### 10d. Verify processed files in S3

```bash
# Check processed outputs
aws s3 ls s3://docfliq-user-content-dev/processed/video/ --recursive
aws s3 ls s3://docfliq-user-content-dev/processed/image/ --recursive
```

---

## 11. Monitoring & Troubleshooting

### View Lambda logs

```bash
# Real-time log tailing
aws logs tail /aws/lambda/docfliq-video-transcode --follow --region ap-south-1
aws logs tail /aws/lambda/docfliq-image-process --follow --region ap-south-1
aws logs tail /aws/lambda/docfliq-transcode-callback --follow --region ap-south-1
```

### Common issues

| Problem | Cause | Fix |
|---------|-------|-----|
| Lambda not triggered on upload | S3 notification not configured or Lambda permission missing | Re-run step 6a and 6b |
| MediaConvert job fails | IAM role doesn't have S3 access | Check docfliq-mediaconvert role has s3:GetObject + s3:PutObject |
| Callback not received | Lambda can't reach media service | Use a public URL or API Gateway for CALLBACK_URL |
| Image Lambda timeout | File too large or memory too low | Increase timeout (max 900s) and memory (up to 3008 MB) |
| "Access Denied" on S3 | Lambda role missing S3 permissions | Check docfliq-lambda-media role policy |

### Update a Lambda function (after code changes)

```bash
# Re-package and update (example: video transcode)
cd lambdas/video_transcode
rm -rf package
pip install -r requirements.txt --target package/ --platform manylinux2014_x86_64 --only-binary=:all:
cp handler.py mediaconvert_job.py package/
cd package && zip -r ../video-transcode.zip . && cd ..

aws lambda update-function-code \
  --function-name docfliq-video-transcode \
  --zip-file fileb://video-transcode.zip \
  --region ap-south-1

rm -rf package video-transcode.zip
```

### Update Lambda environment variables

```bash
aws lambda update-function-configuration \
  --function-name docfliq-video-transcode \
  --environment "Variables={
    MEDIACONVERT_ENDPOINT=<endpoint>,
    MEDIACONVERT_ROLE_ARN=<role-arn>,
    OUTPUT_BUCKET=docfliq-user-content-dev,
    CALLBACK_URL=<your-callback-url>
  }" \
  --region ap-south-1
```

---

## Summary Checklist

- [ ] S3 bucket exists with CORS and lifecycle rules
- [ ] IAM role `docfliq-lambda-media` created with S3 + MediaConvert permissions
- [ ] IAM role `docfliq-mediaconvert` created with S3 read/write
- [ ] MediaConvert endpoint URL saved
- [ ] Lambda `docfliq-video-transcode` deployed
- [ ] Lambda `docfliq-transcode-callback` deployed
- [ ] Lambda `docfliq-image-process` deployed
- [ ] S3 event notifications configured (video + image prefixes)
- [ ] EventBridge rule created for MediaConvert job status changes
- [ ] `.env` updated with MediaConvert endpoint and role ARN
- [ ] Media service running on port 8005
- [ ] Upload + confirm flow tested end-to-end
- [ ] Lambda logs verified in CloudWatch
- [ ] (Later) CloudFront distribution created for production
- [ ] (Later) Virus scan Lambda deployed with ClamAV layer

---
---

# AWS Console (Website) Guide — Step by Step for DevOps

If you prefer using the AWS website instead of CLI, follow this section.
Open https://console.aws.amazon.com and sign in. Make sure you are in the
**Asia Pacific (Mumbai) ap-south-1** region (top-right dropdown).

---

## Step 1: Verify the S3 Bucket

1. Go to **S3** (search "S3" in the top search bar)
2. You should see `docfliq-user-content-dev` in the bucket list
3. Click on it
4. You should see folders like `verification/` (from MS-1). If not, that's fine — folders are created on first upload

### 1a. Set up CORS

1. Inside the bucket, click the **Permissions** tab
2. Scroll down to **Cross-origin resource sharing (CORS)**
3. Click **Edit**
4. Paste this JSON and click **Save changes**:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT", "GET", "HEAD"],
    "AllowedOrigins": ["http://localhost:3000", "https://docfliq.com"],
    "MaxAgeSeconds": 3600,
    "ExposeHeaders": ["ETag"]
  }
]
```

### 1b. Set up Lifecycle Rule

1. Inside the bucket, click the **Management** tab
2. Click **Create lifecycle rule**
3. Fill in:
   - **Rule name**: `abort-incomplete-uploads`
   - **Prefix**: `uploads/`
   - Check **Delete expired object delete markers or incomplete multipart uploads**
   - Check **Delete incomplete multipart uploads**
   - Set **Number of days**: `1`
4. Click **Create rule**

---

## Step 2: Create IAM Roles

Go to **IAM** (search "IAM" in the top search bar)

### 2a. Create the Lambda Execution Role

1. In the left sidebar, click **Roles**
2. Click **Create role**
3. **Trusted entity type**: AWS service
4. **Use case**: Lambda
5. Click **Next**
6. On the "Add permissions" page, **skip** (don't attach any managed policies — we'll add a custom one)
7. Click **Next**
8. **Role name**: `docfliq-lambda-media`
9. **Description**: `Docfliq media processing Lambda execution role`
10. Click **Create role**

Now add the custom permissions:

1. Click on the role name `docfliq-lambda-media` to open it
2. Click the **Permissions** tab
3. Click **Add permissions** → **Create inline policy**
4. Click the **JSON** tab
5. Paste this policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:PutObjectTagging",
        "s3:GetObjectTagging",
        "s3:HeadObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::docfliq-user-content-dev",
        "arn:aws:s3:::docfliq-user-content-dev/*"
      ]
    },
    {
      "Sid": "MediaConvertAccess",
      "Effect": "Allow",
      "Action": [
        "mediaconvert:CreateJob",
        "mediaconvert:GetJob",
        "mediaconvert:ListJobs",
        "mediaconvert:DescribeEndpoints"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Sid": "PassRoleToMediaConvert",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::*:role/docfliq-mediaconvert"
    }
  ]
}
```

6. Click **Next**
7. **Policy name**: `docfliq-lambda-media-policy`
8. Click **Create policy**
9. **Copy the Role ARN** from the top of the page (looks like `arn:aws:iam::123456789012:role/docfliq-lambda-media`). You will need this when creating Lambda functions.

### 2b. Create the MediaConvert Role

1. Go back to **IAM** → **Roles** → **Create role**
2. **Trusted entity type**: Custom trust policy
3. Paste this trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "mediaconvert.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

4. Click **Next**
5. Skip managed policies, click **Next**
6. **Role name**: `docfliq-mediaconvert`
7. **Description**: `Docfliq MediaConvert S3 access role`
8. Click **Create role**

Now add S3 permissions:

1. Click on `docfliq-mediaconvert` to open it
2. Click **Add permissions** → **Create inline policy**
3. Click the **JSON** tab
4. Paste:

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

5. Click **Next**
6. **Policy name**: `docfliq-mediaconvert-s3`
7. Click **Create policy**
8. **Copy the Role ARN** (looks like `arn:aws:iam::123456789012:role/docfliq-mediaconvert`). You will need this for the Lambda environment variables.

---

## Step 3: Get the MediaConvert Endpoint

1. Go to **MediaConvert** (search "MediaConvert" in the top search bar)
2. Make sure you are in **ap-south-1** region
3. In the left sidebar, click **Account**
4. You will see your **API endpoint** — it looks like:
   `https://abc123def.mediaconvert.ap-south-1.amazonaws.com`
5. **Copy this URL** — you will need it for the Lambda environment variables

---

## Step 4: Create Lambda Functions

Go to **Lambda** (search "Lambda" in the top search bar)

### 4a. Create the Video Transcoding Lambda

**First, build the zip file on your local machine:**

```bash
cd /home/bsc/WORK/Scalixity/DOCFLIQ/docfliq-backend/services/media/lambdas/video_transcode
rm -rf package
pip install -r requirements.txt --target package/ --platform manylinux2014_x86_64 --only-binary=:all:
cp handler.py mediaconvert_job.py package/
cd package && zip -r ../video-transcode.zip . && cd ..
```

**Now go to the AWS Console:**

1. Click **Create function**
2. Choose **Author from scratch**
3. **Function name**: `docfliq-video-transcode`
4. **Runtime**: Python 3.12
5. **Architecture**: x86_64
6. **Execution role**: Use an existing role → select `docfliq-lambda-media`
7. Click **Create function**

Upload the code:

1. In the function page, click **Upload from** → **.zip file**
2. Select the `video-transcode.zip` file you created above
3. Click **Save**

Set environment variables:

1. Click the **Configuration** tab
2. Click **Environment variables** in the left sidebar
3. Click **Edit**
4. Add these variables one by one (click **Add environment variable** for each):

| Key | Value |
|-----|-------|
| `MEDIACONVERT_ENDPOINT` | `https://abc123def.mediaconvert.ap-south-1.amazonaws.com` (your endpoint from Step 3) |
| `MEDIACONVERT_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/docfliq-mediaconvert` (your role ARN from Step 2b) |
| `OUTPUT_BUCKET` | `docfliq-user-content-dev` |
| `CALLBACK_URL` | `http://<YOUR_SERVER_IP>:8005/api/v1/internal/media/callback/transcode` |

5. Click **Save**

Set timeout:

1. Still in **Configuration**, click **General configuration** in the left sidebar
2. Click **Edit**
3. Set **Timeout** to `1 min 0 sec`
4. Set **Memory** to `256 MB`
5. Click **Save**

### 4b. Create the MediaConvert Callback Lambda

**Build the zip:**

```bash
cd /home/bsc/WORK/Scalixity/DOCFLIQ/docfliq-backend/services/media/lambdas/video_transcode
rm -rf cb_package
pip install -r requirements.txt --target cb_package/ --platform manylinux2014_x86_64 --only-binary=:all:
cp callback.py cb_package/handler.py
cd cb_package && zip -r ../transcode-callback.zip . && cd ..
```

**In AWS Console:**

1. Go to **Lambda** → **Create function**
2. **Function name**: `docfliq-transcode-callback`
3. **Runtime**: Python 3.12
4. **Execution role**: `docfliq-lambda-media`
5. Click **Create function**
6. **Upload from** → **.zip file** → select `transcode-callback.zip`
7. **Configuration** → **Environment variables** → **Edit** → add:

| Key | Value |
|-----|-------|
| `CALLBACK_URL` | `http://<YOUR_SERVER_IP>:8005/api/v1/internal/media/callback/transcode` |
| `OUTPUT_BUCKET` | `docfliq-user-content-dev` |
| `CLOUDFRONT_DOMAIN` | (leave empty for now) |

8. **General configuration** → Timeout: `30 sec`, Memory: `128 MB`
9. **Save** everything

### 4c. Create the Image Processing Lambda

**Build the zip:**

```bash
cd /home/bsc/WORK/Scalixity/DOCFLIQ/docfliq-backend/services/media/lambdas/image_process
rm -rf package
pip install -r requirements.txt --target package/ --platform manylinux2014_x86_64 --only-binary=:all:
cp handler.py processor.py package/
cd package && zip -r ../image-process.zip . && cd ..
```

**In AWS Console:**

1. Go to **Lambda** → **Create function**
2. **Function name**: `docfliq-image-process`
3. **Runtime**: Python 3.12
4. **Execution role**: `docfliq-lambda-media`
5. Click **Create function**
6. **Upload from** → **.zip file** → select `image-process.zip`
7. **Configuration** → **Environment variables** → **Edit** → add:

| Key | Value |
|-----|-------|
| `OUTPUT_BUCKET` | `docfliq-user-content-dev` |
| `CALLBACK_URL` | `http://<YOUR_SERVER_IP>:8005/api/v1/internal/media/callback/image` |

8. **General configuration** → Timeout: `2 min 0 sec`, Memory: `512 MB`
9. **Save** everything

---

## Step 5: Connect S3 Uploads to Lambda (S3 Event Triggers)

### 5a. Add trigger for Video Transcoding

1. Go to **Lambda** → click `docfliq-video-transcode`
2. Click **Add trigger** (top of the page)
3. **Select a source**: S3
4. **Bucket**: `docfliq-user-content-dev`
5. **Event types**: All object create events
6. **Prefix**: `uploads/video/`
7. **Suffix**: leave empty
8. Check the acknowledgement checkbox
9. Click **Add**

### 5b. Add trigger for Image Processing

1. Go to **Lambda** → click `docfliq-image-process`
2. Click **Add trigger**
3. **Select a source**: S3
4. **Bucket**: `docfliq-user-content-dev`
5. **Event types**: All object create events
6. **Prefix**: `uploads/image/`
7. **Suffix**: leave empty
8. Check the acknowledgement checkbox
9. Click **Add**

### 5c. Verify triggers are set

1. Go to **S3** → `docfliq-user-content-dev` → **Properties** tab
2. Scroll down to **Event notifications**
3. You should see 2 entries:
   - `uploads/video/` → `docfliq-video-transcode`
   - `uploads/image/` → `docfliq-image-process`

---

## Step 6: Set Up EventBridge (MediaConvert Callback)

When MediaConvert finishes a video, AWS sends an event. We need EventBridge
to catch that event and trigger our callback Lambda.

1. Go to **EventBridge** (search "EventBridge" in the top search bar)
2. In the left sidebar, click **Rules**
3. Make sure you're on the **default** event bus
4. Click **Create rule**

### Fill in the rule:

**Step 1 — Define rule detail:**
- **Name**: `docfliq-mediaconvert-job-status`
- **Description**: `Trigger callback when MediaConvert jobs complete or fail`
- **Event bus**: default
- **Rule type**: Rule with an event pattern
- Click **Next**

**Step 2 — Build event pattern:**
- **Event source**: AWS events or EventBridge partner events
- **Creation method**: Custom pattern (JSON editor)
- Paste this pattern:

```json
{
  "source": ["aws.mediaconvert"],
  "detail-type": ["MediaConvert Job State Change"],
  "detail": {
    "status": ["COMPLETE", "ERROR"]
  }
}
```

- Click **Next**

**Step 3 — Select targets:**
- **Target type**: AWS service
- **Select a target**: Lambda function
- **Function**: `docfliq-transcode-callback`
- Click **Next**

**Step 4 — Tags:**
- Skip, click **Next**

**Step 5 — Review and create:**
- Review everything looks correct
- Click **Create rule**

### Verify:

1. You should see `docfliq-mediaconvert-job-status` in the rules list
2. Click on it → **Targets** tab should show `docfliq-transcode-callback`

---

## Step 7: Create the Database

The media service needs its own PostgreSQL database.

1. Connect to your RDS instance using any SQL client (pgAdmin, DBeaver, psql, etc.)
2. Run this SQL:

```sql
CREATE DATABASE media_db;
```

3. Then run the Alembic migration from your local machine:

```bash
cd /home/bsc/WORK/Scalixity/DOCFLIQ/docfliq-backend/migrations/media

MEDIA_DATABASE_URL="postgresql+asyncpg://postgres:MZ6I7%2AUrM476H2u%23Afc%3Ah4Hd%5B82-@devpostgres.c9p1ihxwaj4k.ap-south-1.rds.amazonaws.com:5432/media_db" \
  ../../services/media/.venv/bin/alembic upgrade head
```

4. You should see output like:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 001_initial_media, Initial media_assets table
```

---

## Step 8: Update the .env File

Open `/home/bsc/WORK/Scalixity/DOCFLIQ/docfliq-backend/.env` and add these variables
(some may already be there — just fill in the values):

```env
# MediaConvert — paste your values from Steps 2b and 3
MEDIACONVERT_ENDPOINT=https://YOUR_ENDPOINT.mediaconvert.ap-south-1.amazonaws.com
MEDIACONVERT_ROLE_ARN=arn:aws:iam::YOUR_ACCOUNT_ID:role/docfliq-mediaconvert
MEDIACONVERT_QUEUE_ARN=
MEDIACONVERT_OUTPUT_BUCKET=docfliq-user-content-dev

# CloudFront — leave empty until production
CLOUDFRONT_DOMAIN=
CLOUDFRONT_KEY_PAIR_ID=
CLOUDFRONT_PRIVATE_KEY=
```

---

## Step 9: Start the Media Service and Test

```bash
cd /home/bsc/WORK/Scalixity/DOCFLIQ/docfliq-backend/services/media
./run.sh
```

Open http://localhost:8005/docs in your browser. You should see the Swagger UI
with all the media endpoints.

### Quick test:

1. First get a JWT token by logging in via the identity service (port 8001)
2. In Swagger UI, click **Authorize** and paste your Bearer token
3. Try **POST /api/v1/media/upload** with:
```json
{
  "asset_type": "IMAGE",
  "content_type": "image/jpeg",
  "original_filename": "test.jpg"
}
```
4. You should get back an `upload_url` and `asset_id`

---

## How It All Fits Together — Visual Summary

```
YOU (Developer)                          AWS Console
─────────────                            ───────────

1. Build zip files locally        →      4. Upload zips to Lambda
2. Create IAM roles               →      (done in IAM console)
3. Get MediaConvert endpoint      →      (done in MediaConvert console)
                                         5. Add S3 triggers to Lambda
                                         6. Create EventBridge rule
                                         7. Create database

                    ┌──────────────────────────────────┐
                    │         WHAT HAPPENS AT RUNTIME   │
                    └──────────────────────────────────┘

User uploads video via frontend
        │
        ▼
Frontend calls POST /media/upload (port 8005)
        │
        ▼
Media service returns presigned S3 URL
        │
        ▼
Frontend uploads file directly to S3
(PUT to presigned URL — goes straight to S3, not through our server)
        │
        ▼
Frontend calls POST /media/upload/confirm
        │
        ▼
S3 fires "ObjectCreated" event
        │
        ├──── uploads/video/* ──→ Lambda: docfliq-video-transcode
        │                              │
        │                              ▼
        │                        MediaConvert job created
        │                        (transcodes to 720p, 1080p, 4K HLS + MP4)
        │                              │
        │                              ▼
        │                        MediaConvert finishes
        │                              │
        │                              ▼
        │                        EventBridge catches the event
        │                              │
        │                              ▼
        │                        Lambda: docfliq-transcode-callback
        │                              │
        │                              ▼
        │                        Calls POST /internal/media/callback/transcode
        │                        (updates asset status to COMPLETED + saves URLs)
        │
        └──── uploads/image/* ──→ Lambda: docfliq-image-process
                                       │
                                       ▼
                                 Pillow resizes to thumbnail, medium, large
                                 Converts to WebP
                                       │
                                       ▼
                                 Uploads processed images back to S3
                                       │
                                       ▼
                                 Calls POST /internal/media/callback/image
                                 (updates asset status to COMPLETED + saves URLs)
```

---

## Quick Reference — What Goes Where

| Thing | Where to find it | Where to paste it |
|-------|-------------------|-------------------|
| AWS Account ID | AWS Console → top-right → click your name | Replace `<ACCOUNT_ID>` everywhere |
| MediaConvert endpoint URL | MediaConvert Console → Account | `.env` → `MEDIACONVERT_ENDPOINT` |
| Lambda role ARN | IAM → Roles → `docfliq-lambda-media` → top of page | Lambda creation → Execution role |
| MediaConvert role ARN | IAM → Roles → `docfliq-mediaconvert` → top of page | `.env` → `MEDIACONVERT_ROLE_ARN` and Lambda env vars |
| Your server IP/URL | Your EC2 instance public IP or domain | Lambda env vars → `CALLBACK_URL` |
| S3 bucket name | S3 Console → bucket list | Already set: `docfliq-user-content-dev` |

---

## Order of Operations (Do This Exactly)

```
Step 1  →  Verify S3 bucket + set CORS + lifecycle rule
Step 2  →  Create IAM role: docfliq-lambda-media
Step 3  →  Create IAM role: docfliq-mediaconvert
Step 4  →  Get MediaConvert endpoint URL
Step 5  →  Build Lambda zip files on your machine (3 zips)
Step 6  →  Create Lambda: docfliq-video-transcode (upload zip + set env vars)
Step 7  →  Create Lambda: docfliq-transcode-callback (upload zip + set env vars)
Step 8  →  Create Lambda: docfliq-image-process (upload zip + set env vars)
Step 9  →  Add S3 trigger to docfliq-video-transcode (prefix: uploads/video/)
Step 10 →  Add S3 trigger to docfliq-image-process (prefix: uploads/image/)
Step 11 →  Create EventBridge rule → target: docfliq-transcode-callback
Step 12 →  Create media_db database on RDS
Step 13 →  Run Alembic migration
Step 14 →  Update .env with MediaConvert endpoint + role ARN
Step 15 →  Start media service: ./run.sh
Step 16 →  Test upload flow via Swagger UI at http://localhost:8005/docs
```
