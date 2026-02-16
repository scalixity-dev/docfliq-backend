resource "aws_s3_bucket" "media" {
  bucket = var.media_bucket_name != "" ? var.media_bucket_name : "${var.bucket_prefix}-${var.env_name}-media"
  tags   = { Name = "docfliq-${var.env_name}-media", Env = var.env_name }
}

resource "aws_s3_bucket_versioning" "media" {
  bucket = aws_s3_bucket.media.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket                  = aws_s3_bucket.media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
