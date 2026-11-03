#!/usr/bin/env bash
# Build the UI once and serve UI + API on http://127.0.0.1:8765
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
(cd "$ROOT/frontend" && npm install --no-audit --no-fund && npm run build)
cd "$ROOT/backend"
uv sync
exec uv run uvicorn app.main:app --host "${SUITE_HOST:-127.0.0.1}" --port "${SUITE_PORT:-8765}"
