#!/usr/bin/env bash
set -euo pipefail
PORT="${1:-}"
[ -z "$PORT" ] && { echo "Usage: $0 <port>"; exit 1; }
# Try TERM, then KILL if still bound
PIDS=$(ss -ltnp | awk '/:'"$PORT"' /{print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)
[ -z "$PIDS" ] && { echo "No process on :$PORT"; exit 0; }
for PID in $PIDS; do
  kill -TERM "$PID" 2>/dev/null || true
done
sleep 1
PIDS2=$(ss -ltnp | awk '/:'"$PORT"' /{print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)
[ -z "$PIDS2" ] || for PID in $PIDS2; do kill -9 "$PID" 2>/dev/null || true; done
echo "Port $PORT freed."

