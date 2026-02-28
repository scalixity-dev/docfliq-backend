#!/usr/bin/env bash
set -e

SVC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SVC_NAME="media-worker"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[$SVC_NAME]${NC} $1"; }

# ── Create venv if missing ────────────────────────────────────────────────
cd "$SVC_DIR"
if [ ! -d .venv ]; then
  log "Creating virtual environment..."
  uv venv .venv --python 3.12
fi

# ── Install dependencies ──────────────────────────────────────────────────
log "Installing dependencies..."
uv pip install --python .venv/bin/python -e ".[dev]" --quiet

# ── Start ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}  ╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}  ║   DOCFLIQ Media Worker (ARQ)         ║${NC}"
echo -e "${CYAN}  ╚══════════════════════════════════════╝${NC}"
echo -e "  ${GREEN}Processing: images + videos from Redis queue${NC}"
echo -e "  ${GREEN}Max concurrent jobs: 20 per worker process${NC}"
echo -e "  ${YELLOW}Scale: run multiple instances of this script${NC}"
echo ""

exec .venv/bin/arq app.worker.WorkerSettings
