resource "aws_elasticache_subnet_group" "main" {
  name       = "docfliq-${var.env_name}-redis"
  subnet_ids = var.subnet_ids
}

resource "aws_elasticache_cluster" "main" {
  cluster_id           = "docfliq-${var.env_name}-redis"
  engine               = "redis"
  node_type            = var.node_type
  num_cache_nodes      = var.num_cache_clusters
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  tags = { Name = "docfliq-${var.env_name}-redis", Env = var.env_name }
}
