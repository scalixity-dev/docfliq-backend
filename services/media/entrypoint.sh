#!/usr/bin/env bash
set -e

ROLE="${ROLE:-api}"

case "$ROLE" in
  api)
    echo "[media] Starting API server on port ${PORT:-8005}"
    exec python -m uvicorn app.main:app \
      --host 0.0.0.0 \
      --port "${PORT:-8005}" \
      --workers "${API_WORKERS:-2}" \
      --log-level info
    ;;
  worker)
    echo "[media-worker] Starting ARQ worker (max_jobs=${ARQ_MAX_JOBS:-20})"
    exec python -m arq app.worker.WorkerSettings
    ;;
  *)
    echo "Unknown ROLE=$ROLE. Use 'api' or 'worker'."
    exit 1
    ;;
esac
