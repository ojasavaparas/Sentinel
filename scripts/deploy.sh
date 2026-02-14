#!/usr/bin/env bash
set -euo pipefail

# Deploy Sentinel to ECS Fargate
# Usage: ./scripts/deploy.sh

REGION="${AWS_REGION:-us-east-1}"
REPO_NAME="sentinel"

echo "==> Getting AWS account ID..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}"

echo "==> Logging into ECR..."
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "==> Building Docker image..."
docker build -t "${REPO_NAME}:latest" .

echo "==> Tagging image..."
docker tag "${REPO_NAME}:latest" "${ECR_URI}:latest"

echo "==> Pushing to ECR..."
docker push "${ECR_URI}:latest"

echo "==> Forcing new ECS deployment..."
aws ecs update-service \
  --cluster sentinel-cluster \
  --service SentinelStack-SentinelService* \
  --force-new-deployment \
  --region "${REGION}" \
  --query "service.serviceName" \
  --output text

echo "==> Deploy complete! Image pushed and new deployment triggered."
