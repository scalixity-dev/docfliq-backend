resource "aws_opensearch_domain" "main" {
  domain_name    = "${var.domain_name}-${var.env_name}"
  engine_version = "OpenSearch_2.11"
  cluster_config { instance_type = var.instance_type; instance_count = 1 }
  vpc_options {
    subnet_ids         = [var.subnet_ids[0]]
    security_group_ids = [aws_security_group.opensearch.id]
  }
  ebs_options { ebs_enabled = true; volume_size = 10; volume_type = "gp3" }
  tags = { Name = "docfliq-${var.env_name}-opensearch", Env = var.env_name }
}

resource "aws_security_group" "opensearch" {
  name   = "docfliq-${var.env_name}-opensearch-sg"
  vpc_id = var.vpc_id
  ingress { from_port = 443; to_port = 443; protocol = "tcp"; cidr_blocks = ["10.0.0.0/16"] }
  tags = { Name = "docfliq-${var.env_name}-opensearch-sg", Env = var.env_name }
}
