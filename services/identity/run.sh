#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$BACKEND_ROOT"

IMAGE_NAME="docfliq-identity"
CONTAINER_NAME="docfliq-identity"
PORT=8001

# Stop existing container if running
if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
  echo "Stopping existing $CONTAINER_NAME container..."
  docker stop "$CONTAINER_NAME" && docker rm "$CONTAINER_NAME"
fi

# Build image from backend root (Dockerfile expects shared/ and services/ at context root)
echo "Building $IMAGE_NAME..."
docker build -f services/identity/Dockerfile -t "$IMAGE_NAME" .

# Run with host networking so it can reach Postgres, Redis, OpenSearch on localhost
echo "Starting $CONTAINER_NAME on port $PORT..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --network host \
  --env-file .env \
  --restart unless-stopped \
  "$IMAGE_NAME" \
  uvicorn app.main:app --host 0.0.0.0 --port "$PORT"

echo "Identity service running at http://localhost:$PORT"
echo "Logs: docker logs -f $CONTAINER_NAME"
