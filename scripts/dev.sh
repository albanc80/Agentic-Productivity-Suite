#!/usr/bin/env bash
# Build the UI once and serve UI + API on http://127.0.0.1:8765
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${SUITE_HOST:-127.0.0.1}"
if [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" && -z "${SUITE_API_TOKEN:-}" ]]; then
  echo "Refusing to listen on $HOST without SUITE_API_TOKEN. Set a long random token first." >&2
  exit 1
fi
(cd "$ROOT/frontend" && npm install --no-audit --no-fund && npm run build)
cd "$ROOT/backend"
uv sync
exec uv run uvicorn app.main:app --host "$HOST" --port "${SUITE_PORT:-8765}"
