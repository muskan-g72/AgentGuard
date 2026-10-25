#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8135}"
HOST="${HOST:-127.0.0.1}"
LIVE=0

for arg in "$@"; do
    case "$arg" in
        --live)
            LIVE=1
            ;;
        --port=*)
            PORT="${arg#*=}"
            ;;
        --host=*)
            HOST="${arg#*=}"
            ;;
    esac
done

if [ "$LIVE" -eq 1 ]; then
    export REPLAY=0
    echo "Starting in LIVE mode (REPLAY=0)"
else
    export REPLAY=1
    echo "Starting in REPLAY mode (REPLAY=1)"
fi

if command -v nc >/dev/null 2>&1; then
    if nc -z "$HOST" "$PORT" 2>/dev/null; then
        echo "Error: Port $PORT is already in use on $HOST" >&2
        exit 1
    fi
elif command -v lsof >/dev/null 2>&1; then
    if lsof -i :"$PORT" >/dev/null 2>&1; then
        echo "Error: Port $PORT is already in use" >&2
        exit 1
    fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "Starting AgentGuard FastAPI application on $HOST:$PORT..."
python -m uvicorn app.main:app --host "$HOST" --port "$PORT" &
APP_PID=$!

cleanup() {
    echo "Stopping server (PID $APP_PID)..."
    kill "$APP_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

HEALTH_URL="http://${HOST}:${PORT}/health"
echo -n "Waiting for application to become ready..."
ATTEMPTS=0
MAX_ATTEMPTS=40
HEALTHY=0

while [ "$ATTEMPTS" -lt "$MAX_ATTEMPTS" ]; do
    sleep 0.5
    echo -n "."
    if curl -s -f -o /dev/null "$HEALTH_URL" 2>/dev/null; then
        HEALTHY=1
        break
    fi
    ATTEMPTS=$((ATTEMPTS + 1))
done
echo ""

if [ "$HEALTHY" -ne 1 ]; then
    echo "Error: Application failed to respond at $HEALTH_URL" >&2
    exit 1
fi

echo ""
echo "======================================================="
echo " AgentGuard Demo is running!"
echo " Food Demo Panel: http://${HOST}:${PORT}/food-demo/"
echo " FoodHub Site:    http://${HOST}:${PORT}/foodhub/"
echo " QuickBite Site:  http://${HOST}:${PORT}/quickbite/"
echo " DineDash Site:   http://${HOST}:${PORT}/dinedash/"
echo " Process ID:      $APP_PID"
echo " Press Ctrl+C to stop."
echo "======================================================="
echo ""

wait "$APP_PID"
