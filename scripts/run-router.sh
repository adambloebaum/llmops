#!/usr/bin/env bash
# Start the local-agent-router. Stdlib-only — no venv, no pip install.
#
# Derives bind/upstream URLs from the llmops registry + host detection.
# Env var overrides (all optional):
#   ROUTER_HOST        bind host (default: detected Tailscale IP)
#   ROUTER_PORT        bind port (default: 8090)
#   ROUTER_EXEC_URL    upstream qwen3.5-4b /v1 base (default: from registry)
#   ROUTER_SMART_URL   upstream qwen3.5-9b /v1 base (default: from registry)
#   ROUTER_API_KEY     if set, require Bearer match
#   ROUTER_LOG_PATH    JSONL telemetry path (default: router/logs/router.jsonl)

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Resolve defaults from the llmops registry + host detection.
eval "$(python3 - <<'PY'
import sys
sys.path.insert(0, ".")
from llmops import host, registry
h = host.load(__import__("pathlib").Path("."))
m = registry.load(__import__("pathlib").Path("models.toml"))
print(f"DEFAULT_HOST={h.bind_ip}")
if "qwen3.5-4b" in m:
    print(f"DEFAULT_EXEC_URL=http://{h.bind_ip}:{m['qwen3.5-4b'].port}/v1")
if "qwen3.5-9b" in m:
    print(f"DEFAULT_SMART_URL=http://{h.bind_ip}:{m['qwen3.5-9b'].port}/v1")
PY
)"

export ROUTER_HOST="${ROUTER_HOST:-${DEFAULT_HOST:-127.0.0.1}}"
export ROUTER_PORT="${ROUTER_PORT:-8090}"
export ROUTER_EXEC_URL="${ROUTER_EXEC_URL:-${DEFAULT_EXEC_URL:-http://127.0.0.1:8080/v1}}"
export ROUTER_SMART_URL="${ROUTER_SMART_URL:-${DEFAULT_SMART_URL:-http://127.0.0.1:8081/v1}}"

mkdir -p "$ROOT/router/logs"
exec python3 -m router.server
