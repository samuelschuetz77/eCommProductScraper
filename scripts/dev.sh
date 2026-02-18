#!/usr/bin/env bash
# POSIX helper for non-Windows environments (optional)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Starting Postgres (docker compose)..."
docker compose up -d

echo "Starting backend (in background)..."
.venv/Scripts/python.exe app.py &

echo "Starting frontend (in background)..."
(cd frontend && npm run dev) &

sleep 1
if command -v xdg-open >/dev/null; then
  xdg-open http://localhost:5173/
elif command -v open >/dev/null; then
  open http://localhost:5173/
fi

echo "Started. Check terminals for logs."