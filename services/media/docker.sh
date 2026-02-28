#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Docfliq Media Service — Docker build & run
#
# Usage:
#   bash docker.sh              Build and start API + 1 worker (default)
#   bash docker.sh --scale      Build and start API + 3 workers
#   bash docker.sh --scale 5    Build and start API + 5 workers
#   bash docker.sh down         Stop all containers
#   bash docker.sh logs         Tail logs from all containers
#   bash docker.sh status       Show running containers
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[media-docker]${NC} $1"; }
warn() { echo -e "${YELLOW}[media-docker]${NC} $1"; }
err()  { echo -e "${RED}[media-docker]${NC} $1"; }

# ── Parse arguments ──────────────────────────────────────────────────────────
CMD="${1:-up}"
WORKERS=1

case "$CMD" in
  --scale)
    CMD="up"
    WORKERS="${2:-3}"
    ;;
  up)
    WORKERS="${2:-1}"
    ;;
esac

# ── Pre-flight checks ───────────────────────────────────────────────────────
check_redis() {
    # Extract host:port from REDIS_URL in .env
    REDIS_URL=$(grep -E '^REDIS_URL=' ../../.env 2>/dev/null | cut -d= -f2-)
    if [ -z "$REDIS_URL" ]; then
        err "REDIS_URL not found in .env"
        exit 1
    fi

    # Parse host and port from redis://host:port/db
    REDIS_HOST=$(echo "$REDIS_URL" | sed -E 's|redis://([^:/@]+).*|\1|')
    REDIS_PORT=$(echo "$REDIS_URL" | sed -E 's|redis://[^:]+:([0-9]+).*|\1|')
    REDIS_PORT="${REDIS_PORT:-6379}"

    if command -v redis-cli &>/dev/null; then
        if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping &>/dev/null; then
            log "Redis reachable at ${REDIS_HOST}:${REDIS_PORT}"
        else
            err "Redis NOT reachable at ${REDIS_HOST}:${REDIS_PORT}"
            err "Workers need Redis for the job queue. Start Redis first."
            exit 1
        fi
    else
        warn "redis-cli not found — skipping Redis check"
    fi
}

# ── Commands ─────────────────────────────────────────────────────────────────
case "$CMD" in
  up)
    echo ""
    echo -e "${CYAN}  ╔═════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}  ║   DOCFLIQ Media Service — Docker            ║${NC}"
    echo -e "${CYAN}  ╚═════════════════════════════════════════════╝${NC}"
    echo ""

    # Check .env exists
    if [ ! -f ../../.env ]; then
        err "../../.env not found. Create it with required env vars."
        exit 1
    fi

    check_redis

    log "Building image..."
    docker compose build

    log "Starting API + ${WORKERS} worker(s)..."
    docker compose up -d --scale media-worker="$WORKERS"

    echo ""
    log "Services running:"
    echo -e "  ${GREEN}API:${NC}     http://localhost:8005/docs"
    echo -e "  ${GREEN}Workers:${NC} ${WORKERS} instance(s) processing from Redis queue"
    echo ""
    echo -e "  ${YELLOW}View logs:${NC}   bash docker.sh logs"
    echo -e "  ${YELLOW}Scale up:${NC}    bash docker.sh --scale 5"
    echo -e "  ${YELLOW}Stop:${NC}        bash docker.sh down"
    echo ""

    # Show container status
    docker compose ps
    ;;

  down)
    log "Stopping all media containers..."
    docker compose down
    log "Done."
    ;;

  logs)
    docker compose logs -f --tail 100
    ;;

  status)
    docker compose ps
    ;;

  restart)
    log "Restarting..."
    docker compose down
    docker compose up -d --scale media-worker="${WORKERS}"
    docker compose ps
    ;;

  *)
    echo "Usage: bash docker.sh [up|down|logs|status|restart|--scale N]"
    exit 1
    ;;
esac
