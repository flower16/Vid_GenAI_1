#!/usr/bin/env bash
# One-process startup for Replit (and any single-container host):
#   1. install backend deps           2. build the frontend (served same-origin)
#   3. run FastAPI on $PORT           (API under /api + /health, UI at /)
#
# Secrets (LANGSMITH_API_KEY, FIREWORKS_API_KEY, SNOWFLAKE_*, AZURE_*,
# PINECONE_API_KEY, ...) come from the Replit Secrets pane as env vars.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8000}"

echo "==> Installing backend dependencies"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r "$ROOT/backend/requirements.txt"

echo "==> Building frontend (same-origin API)"
pushd "$ROOT/frontend" >/dev/null
if [ ! -d node_modules ]; then npm ci || npm install; fi
# Empty API URL => axios uses the current origin (FastAPI serves the UI).
VITE_API_URL="" npm run build
popd >/dev/null

echo "==> Starting FastAPI on :$PORT"
cd "$ROOT/backend"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
