#!/usr/bin/env bash
# Starts MongoDB (if not already running), the FastAPI backend, and the React
# dev server (which opens your browser). Ctrl-C stops everything cleanly.
set -euo pipefail
set -m  # each backgrounded job gets its own process group, so `kill -$pid`
        # in cleanup() reaches mongod/craco's forked children too — macOS
        # has no `setsid` to do this the Linux way.
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -f backend/.env ]; then
  echo "backend/.env not found — run ./setup.sh first." >&2
  exit 1
fi
if [ ! -d backend/venv ]; then
  echo "backend/venv not found — run ./setup.sh first." >&2
  exit 1
fi

PIDS=()
cleanup() {
  echo ""
  echo "==> Shutting down…"
  for pid in "${PIDS[@]:-}"; do
    # kill the whole process group, not just the wrapper shell — uvicorn
    # --reload and craco both fork children that survive a plain `kill`.
    kill -- "-$pid" >/dev/null 2>&1 || kill "$pid" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT INT TERM

free_port() {
  local port="$1" pid
  pid=$(lsof -ti ":$port" 2>/dev/null || true)
  if [ -n "$pid" ]; then
    echo "Port $port was in use by a leftover process (pid $pid) — stopping it."
    kill -9 $pid >/dev/null 2>&1 || true
    sleep 1
  fi
}

echo "==> MongoDB"
free_port 27017
mkdir -p .mongo-data
mongod --dbpath .mongo-data --logpath .mongo-data/mongod.log --port 27017 &
PIDS+=($!)
echo "Starting local mongod (pid $!)…"
for _ in $(seq 1 20); do
  (echo > /dev/tcp/127.0.0.1/27017) >/dev/null 2>&1 && break
  sleep 0.5
done

echo "==> Backend (FastAPI)"
free_port 8000
(cd backend && exec ../backend/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000) &
PIDS+=($!)

echo "Waiting for backend health check…"
for _ in $(seq 1 40); do
  if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

echo "==> Frontend (opens your browser)"
free_port 3000
(cd frontend && yarn start)
