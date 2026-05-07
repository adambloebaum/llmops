#!/usr/bin/env bash
# Activate the exec tier (Qwen3.5-4B). Stops smart if running.
# Spec: exec is the always-on default; smart spins up on demand.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
docker compose stop smart >/dev/null 2>&1 || true
docker compose --profile default up -d exec
echo "[ok] exec active on \${LLM_BIND_HOST}:\${EXEC_PORT}"
