#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

usage() {
  echo "Usage: ./deploy.sh [service|all|nginx|ssl]"
  echo ""
  echo "Services:"
  echo "  identity    - Rebuild & restart identity service (port 8000)"
  echo "  content     - Rebuild & restart content service  (port 8001)"
  echo "  media       - Rebuild & restart media service    (port 8005)"
  echo "  all         - Rebuild & restart all services"
  echo "  nginx       - Restart nginx with latest config"
  echo "  ssl         - Setup SSL certificate via certbot"
  echo "  status      - Show status of all containers"
  echo "  logs [svc]  - Tail logs for a service"
  echo ""
  echo "Examples:"
  echo "  ./deploy.sh identity        # redeploy identity after .env change"
  echo "  ./deploy.sh all             # redeploy everything"
  echo "  ./deploy.sh nginx           # reload nginx config"
  echo "  ./deploy.sh logs identity   # tail identity logs"
}

deploy_service() {
  local svc="$1"
  echo "=== Deploying $svc ==="
  bash "services/$svc/run.sh"
  echo ""
}

deploy_nginx() {
  echo "=== Deploying nginx ==="
  local CONTAINER_NAME="docfliq-nginx"

  if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
    echo "Stopping existing $CONTAINER_NAME..."
    docker stop "$CONTAINER_NAME" && docker rm "$CONTAINER_NAME"
  elif docker ps -aq -f name="$CONTAINER_NAME" | grep -q .; then
    docker rm "$CONTAINER_NAME"
  fi

  # Create certbot webroot if it doesn't exist
  sudo mkdir -p /var/www/certbot

  docker run -d \
    --name "$CONTAINER_NAME" \
    --network host \
    --restart unless-stopped \
    -v "$SCRIPT_DIR/nginx.ec2.conf:/etc/nginx/conf.d/default.conf:ro" \
    -v /var/www/certbot:/var/www/certbot:ro \
    -v /etc/letsencrypt:/etc/letsencrypt:ro \
    nginx:1.25-alpine

  echo "Nginx running on port 80 -> docfliq2.com"
}

setup_ssl() {
  echo "=== Setting up SSL for docfliq2.com ==="
  sudo certbot certonly --webroot -w /var/www/certbot -d docfliq2.com
  echo ""
  echo "SSL certificate obtained. Now:"
  echo "  1. Uncomment the HTTPS server block in nginx.ec2.conf"
  echo "  2. Run: ./deploy.sh nginx"
}

show_status() {
  echo "=== Service Status ==="
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" \
    --filter "name=docfliq-"
}

show_logs() {
  local svc="${1:-}"
  if [ -z "$svc" ]; then
    echo "Usage: ./deploy.sh logs [identity|content|media|nginx]"
    exit 1
  fi
  docker logs -f "docfliq-$svc"
}

case "${1:-}" in
  identity)  deploy_service identity ;;
  content)   deploy_service content ;;
  media)     deploy_service media ;;
  all)
    deploy_service identity
    deploy_service content
    deploy_service media
    deploy_nginx
    echo "=== All services deployed ==="
    show_status
    ;;
  nginx)     deploy_nginx ;;
  ssl)       setup_ssl ;;
  status)    show_status ;;
  logs)      show_logs "$2" ;;
  *)         usage ;;
esac
