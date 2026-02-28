#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$BACKEND_ROOT"

IMAGE_NAME="docfliq-content"
CONTAINER_NAME="docfliq-content"
PORT=8001

# Stop existing container if running
if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
  echo "Stopping existing $CONTAINER_NAME container..."
  docker stop "$CONTAINER_NAME" && docker rm "$CONTAINER_NAME"
elif docker ps -aq -f name="$CONTAINER_NAME" | grep -q .; then
  docker rm "$CONTAINER_NAME"
fi

# Build image
echo "Building $IMAGE_NAME..."
docker build -f services/content/Dockerfile -t "$IMAGE_NAME" .

# Run with host networking, bind to 127.0.0.1 (not exposed externally)
echo "Starting $CONTAINER_NAME on 127.0.0.1:$PORT..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --network host \
  --env-file .env \
  --restart unless-stopped \
  "$IMAGE_NAME" \
  uvicorn app.main:app --host 127.0.0.1 --port "$PORT"

echo "Content service running at http://127.0.0.1:$PORT"
echo "Logs: docker logs -f $CONTAINER_NAME"
