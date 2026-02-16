# Docfliq infra root — delegates to environment
# Run from infra/environments/dev|uat|prod for actual apply

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # backend "s3" { ... } — configure per environment
}

output "note" {
  value = "Run terraform from infra/environments/dev, uat, or prod"
}
