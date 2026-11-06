#!/usr/bin/env bash
# Dev servers that can't touch production:
#   API  :8001  ONS_DEV=1 → write logs go to .dev-data/ (seeded from data/ on first run), not data/
#   web  :3001  NEXT_DIST_DIR=.next-dev → never overwrites web/.next, which launchd's `next start` serves
# Reads still come from the real warehouse (read-only DuckDB). Ctrl-C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -d .dev-data ]; then
  mkdir -p .dev-data
  for d in habits checkin inbox; do [ -d "data/$d" ] && cp -R "data/$d" .dev-data/; done
  echo "Seeded .dev-data/ from data/ (habits, checkin, inbox)."
fi

export ONS_DEV=1
.venv/bin/uvicorn api.main:app --port 8001 --reload &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT

cd web
NEXT_DIST_DIR=.next-dev NEXT_PUBLIC_API_BASE=http://localhost:8001/api npx next dev -p 3001
