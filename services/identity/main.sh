#!/usr/bin/env bash
set -e

SVC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SVC_NAME="identity"
PORT=8001

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[$SVC_NAME]${NC} $1"; }
warn() { echo -e "${YELLOW}[$SVC_NAME]${NC} $1"; }
err()  { echo -e "${RED}[$SVC_NAME]${NC} $1"; }

# ── Kill existing process on port ─────────────────────────────────────────────
pids=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [ -n "$pids" ]; then
  warn "Killing existing process(es) on port $PORT (PIDs: $pids)"
  echo "$pids" | xargs kill -9 2>/dev/null || true
  sleep 1
fi

# ── Create venv if missing ────────────────────────────────────────────────────
cd "$SVC_DIR"
if [ ! -d .venv ]; then
  log "Creating virtual environment..."
  uv venv .venv --python 3.12
fi

# ── Install dependencies ──────────────────────────────────────────────────────
log "Installing dependencies..."
uv pip install --python .venv/bin/python -e ".[dev]" --quiet

# ── Start ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}  ╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}  ║    DOCFLIQ Identity Service (MS-1)   ║${NC}"
echo -e "${CYAN}  ╚══════════════════════════════════════╝${NC}"
echo -e "  ${GREEN}http://localhost:${PORT}/docs${NC}"
echo ""

exec .venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --reload
