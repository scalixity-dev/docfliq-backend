terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = { source = "hashicorp/aws"; version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" { type = string; default = "us-east-1" }
variable "env_name" { type = string; default = "dev" }

module "vpc" {
  source               = "../../modules/vpc"
  env_name             = var.env_name
  vpc_cidr             = "10.0.0.0/16"
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
  private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]
}

module "s3" {
  source   = "../../modules/s3"
  env_name = var.env_name
}

variable "availability_zones" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}

output "vpc_id" { value = module.vpc.vpc_id }
output "public_subnet_ids" { value = module.vpc.public_subnet_ids }
output "private_subnet_ids" { value = module.vpc.private_subnet_ids }
output "media_bucket_id" { value = module.s3.media_bucket_id }
