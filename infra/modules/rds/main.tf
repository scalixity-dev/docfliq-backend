resource "aws_db_subnet_group" "main" {
  name       = "docfliq-${var.env_name}-rds"
  subnet_ids = var.subnet_ids
  tags = { Name = "docfliq-${var.env_name}-rds-subnet", Env = var.env_name }
}

resource "aws_security_group" "rds" {
  name   = "docfliq-${var.env_name}-rds-sg"
  vpc_id = var.vpc_id
  ingress { from_port = 5432; to_port = 5432; protocol = "tcp"; cidr_blocks = ["10.0.0.0/16"] }
  egress { from_port = 0; to_port = 0; protocol = "-1"; cidr_blocks = ["0.0.0.0/0"] }
  tags = { Name = "docfliq-${var.env_name}-rds-sg", Env = var.env_name }
}

resource "aws_db_instance" "main" {
  identifier             = "docfliq-${var.env_name}"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = var.instance_class
  allocated_storage      = var.allocated_storage
  db_name                = var.database_name
  username               = var.username
  password               = var.password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  skip_final_snapshot    = var.env_name != "prod"
  tags = { Name = "docfliq-${var.env_name}-rds", Env = var.env_name }
}
