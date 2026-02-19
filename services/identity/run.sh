#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Docfliq Identity — setup and run"

# Ensure uv is available
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Install from https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Create venv if missing
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    uv venv
fi

# Sync dependencies (includes editable docfliq-shared from ../../shared)
echo "📥 Syncing dependencies..."
uv sync

# Free port 8001 if already in use (don't let lsof/fuser exit code kill the script)
PORT=8001
if command -v lsof &> /dev/null; then
  PID=$(lsof -ti:"$PORT" 2>/dev/null) || true
  if [ -n "$PID" ]; then
    echo "🔌 Killing process $PID on port $PORT..."
    kill $PID 2>/dev/null || true
    sleep 1
  fi
elif command -v fuser &> /dev/null; then
  fuser -k "$PORT/tcp" 2>/dev/null || true
  sleep 1
fi

# Run identity service (port 8001 to match Makefile)
echo "✨ Starting Identity service on http://0.0.0.0:8001"
exec uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001 "$@"
