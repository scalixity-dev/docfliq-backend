#!/usr/bin/env bash
# Health-check all services on localhost (ports 8001-8006)
# Exit 0 if all return 200, else 1
set -euo pipefail

BASE="${1:-http://localhost}"
PORTS="8001 8002 8003 8004 8005 8006"
FAIL=0

for port in $PORTS; do
  url="${BASE}:${port}/health"
  if curl -sf --max-time 5 "$url" >/dev/null; then
    echo "OK $url"
  else
    echo "FAIL $url"
    FAIL=1
  fi
done

exit $FAIL
