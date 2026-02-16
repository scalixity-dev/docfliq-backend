resource "aws_ecs_cluster" "main" {
  name = "${var.cluster_name}-${var.env_name}"
  setting { name = "containerInsights"; value = "enabled" }
  tags = { Name = "docfliq-${var.env_name}-ecs", Env = var.env_name }
}

data "aws_region" "current" {}

resource "aws_ecs_task_definition" "main" {
  family                   = "docfliq-${var.env_name}-${var.service_name}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.task_cpu
  memory                    = var.task_memory
  container_definitions = jsonencode([{
    name = var.service_name
    image = var.container_image
    essential = true
    portMappings = [{ containerPort = var.container_port; protocol = "tcp" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group" = "/ecs/docfliq-${var.env_name}"
        "awslogs-region" = data.aws_region.current.name
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
  tags = { Name = "docfliq-${var.env_name}-${var.service_name}", Env = var.env_name }
}

resource "aws_ecs_service" "main" {
  name            = "docfliq-${var.env_name}-${var.service_name}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.main.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = var.target_group_arn
    container_name   = var.service_name
    container_port   = var.container_port
  }
  tags = { Name = "docfliq-${var.env_name}-${var.service_name}", Env = var.env_name }
}
