#!/usr/bin/env bash
# Deploy Docfliq backend to dev | uat | prod
# Usage: ./scripts/deploy.sh <env>
set -euo pipefail

ENV="${1:-dev}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

case "$ENV" in
  dev|uat|prod) ;;
  *) echo "Usage: $0 dev|uat|prod"; exit 1 ;;
esac

echo "==> Deploying to $ENV"

# Build and push Docker images (when ECR/registry configured)
# Uncomment and set ECR_URI when using AWS ECR:
# ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/docfliq"
# for svc in identity content course webinar payment platform; do
#   docker build -f "services/$svc/Dockerfile" -t "$ECR_URI-$svc:latest" .
#   docker push "$ECR_URI-$svc:latest"
# done

# Terraform apply for the environment
if command -v terraform &>/dev/null; then
  echo "==> Running Terraform in infra/environments/$ENV"
  cd "infra/environments/$ENV"
  terraform init -input=false
  terraform plan -input=false -out=tfplan
  terraform apply -input=false tfplan
  cd "$REPO_ROOT"
else
  echo "==> Terraform not found; skipping infra apply"
fi

echo "==> Deploy to $ENV complete"
