#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Docfliq Media Processing — setup and run"

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

# Free port 8005 if already in use
PORT=8005
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

# Run media service (port 8005)
echo "✨ Starting Media Processing service on http://0.0.0.0:8005"
exec uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8005 "$@"
