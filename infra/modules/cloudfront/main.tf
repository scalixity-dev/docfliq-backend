resource "aws_cloudfront_distribution" "main" {
  enabled = true
  origin {
    domain_name = var.origin_domain
    origin_id   = var.origin_id
  }
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = var.origin_id
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
  }
  restrictions { geo_restriction { restriction_type = "none" } }
  viewer_certificate { cloudfront_default_certificate = true }
  tags = { Name = "docfliq-${var.env_name}-cdn", Env = var.env_name }
}
