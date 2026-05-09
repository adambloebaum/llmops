#!/usr/bin/env bash
# Start the local-agent-router. Stdlib-only — no venv, no pip install.
#
# Env vars (all optional):
#   ROUTER_HOST        bind host (default: ${LLM_BIND_HOST:-100.114.124.62})
#   ROUTER_PORT        bind port (default: 8090)
#   ROUTER_EXEC_URL    upstream exec /v1 base (default: http://127.0.0.1:8080/v1)
#   ROUTER_SMART_URL   upstream smart /v1 base (default: http://127.0.0.1:8081/v1)
#   ROUTER_API_KEY     if set, require Bearer match
#   ROUTER_LOG_PATH    JSONL telemetry path (default: router/logs/router.jsonl)

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export ROUTER_HOST="${ROUTER_HOST:-${LLM_BIND_HOST:-100.114.124.62}}"
export ROUTER_PORT="${ROUTER_PORT:-8090}"
# upstream tiers are bound to ${LLM_BIND_HOST} by compose, not 127.0.0.1
export ROUTER_EXEC_URL="${ROUTER_EXEC_URL:-http://${LLM_BIND_HOST:-100.114.124.62}:${EXEC_PORT:-8080}/v1}"
export ROUTER_SMART_URL="${ROUTER_SMART_URL:-http://${LLM_BIND_HOST:-100.114.124.62}:${SMART_PORT:-8081}/v1}"

mkdir -p "$ROOT/router/logs"
exec python3 -m router.server
