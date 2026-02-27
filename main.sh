#!/usr/bin/env bash
set -e

BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_ROOT"

# ── Services to start ─────────────────────────────────────────────────────────
declare -A SERVICES=(
  [identity]=8001
  [media]=8005
)

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[main]${NC} $1"; }
warn() { echo -e "${YELLOW}[main]${NC} $1"; }
err()  { echo -e "${RED}[main]${NC} $1"; }

# ── Kill any process on a given port ──────────────────────────────────────────
kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    warn "Killing existing process(es) on port $port (PIDs: $pids)"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
}

# ── Setup venv + install deps for a service ───────────────────────────────────
setup_service() {
  local name=$1
  local svc_dir="$BACKEND_ROOT/services/$name"

  log "Setting up $name service..."

  if [ ! -d "$svc_dir/.venv" ]; then
    log "Creating venv for $name..."
    uv venv "$svc_dir/.venv" --python 3.12
  fi

  log "Installing dependencies for $name..."
  cd "$svc_dir"
  uv pip install --python .venv/bin/python -e ".[dev]" --quiet
  cd "$BACKEND_ROOT"
}

# ── Start a service in the background ─────────────────────────────────────────
start_service() {
  local name=$1
  local port=$2
  local svc_dir="$BACKEND_ROOT/services/$name"
  local log_file="$BACKEND_ROOT/.logs/${name}.log"

  mkdir -p "$BACKEND_ROOT/.logs"

  kill_port "$port"

  log "Starting $name on port $port..."
  cd "$svc_dir"
  .venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$port" \
    --reload \
    > "$log_file" 2>&1 &

  local pid=$!
  echo "$pid" > "$BACKEND_ROOT/.logs/${name}.pid"
  cd "$BACKEND_ROOT"

  # Wait briefly and check it started
  sleep 2
  if kill -0 "$pid" 2>/dev/null; then
    log "${name} running (PID: $pid, port: $port)"
  else
    err "${name} failed to start! Check: tail -50 $log_file"
    return 1
  fi
}

# ── Stop all services ─────────────────────────────────────────────────────────
stop_all() {
  log "Stopping all services..."
  for name in "${!SERVICES[@]}"; do
    local pid_file="$BACKEND_ROOT/.logs/${name}.pid"
    if [ -f "$pid_file" ]; then
      local pid
      pid=$(cat "$pid_file")
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        log "Stopped $name (PID: $pid)"
      fi
      rm -f "$pid_file"
    fi
    kill_port "${SERVICES[$name]}"
  done
}

# ── Handle Ctrl+C ────────────────────────────────────────────────────────────
trap stop_all EXIT INT TERM

# ── Main ──────────────────────────────────────────────────────────────────────
case "${1:-start}" in
  stop)
    stop_all
    exit 0
    ;;
  start)
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════╗"
    echo "  ║       DOCFLIQ Backend Services       ║"
    echo "  ╚══════════════════════════════════════╝"
    echo -e "${NC}"

    # Setup all services
    for name in "${!SERVICES[@]}"; do
      setup_service "$name"
    done

    echo ""

    # Start all services
    for name in "${!SERVICES[@]}"; do
      start_service "$name" "${SERVICES[$name]}"
    done

    echo ""
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo -e "  Identity : ${CYAN}http://localhost:8001/docs${NC}"
    echo -e "  Media    : ${CYAN}http://localhost:8005/docs${NC}"
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo ""
    log "Logs: tail -f .logs/identity.log .logs/media.log"
    log "Stop: ./main.sh stop  (or Ctrl+C)"
    echo ""

    # Keep script alive — forward logs
    tail -f .logs/identity.log .logs/media.log 2>/dev/null
    ;;
  *)
    echo "Usage: ./main.sh [start|stop]"
    exit 1
    ;;
esac
