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
variable "env_name" { type = string; default = "uat" }
variable "availability_zones" { type = list(string); default = ["us-east-1a", "us-east-1b"] }

module "vpc" {
  source               = "../../modules/vpc"
  env_name             = var.env_name
  vpc_cidr             = "10.1.0.0/16"
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = ["10.1.1.0/24", "10.1.2.0/24"]
  private_subnet_cidrs = ["10.1.10.0/24", "10.1.11.0/24"]
}

module "s3" {
  source   = "../../modules/s3"
  env_name = var.env_name
}

output "vpc_id" { value = module.vpc.vpc_id }
output "media_bucket_id" { value = module.s3.media_bucket_id }
