#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

EXEC_BASE="http://${LLM_BIND_HOST:-127.0.0.1}:${EXEC_PORT:-8080}"
SMART_BASE="http://${LLM_BIND_HOST:-127.0.0.1}:${SMART_PORT:-8081}"

probe() {
  local label="$1" base="$2"
  echo "== ${label} (${base}) =="
  if curl -fsS --max-time 3 "${base}/health" >/dev/null; then
    echo "  health: ok"
  else
    echo "  health: failed"
    return
  fi
  if curl -fsS --max-time 5 "${base}/v1/models" >/tmp/local-llm-models-${label}.json; then
    sed -n 's/.*"id":"\([^"]*\)".*/  model: \1/p' /tmp/local-llm-models-${label}.json | head -1
  fi
  if curl -fsS --max-time 5 "${base}/props" >/tmp/local-llm-props-${label}.json 2>/dev/null; then
    sed -n 's/.*"n_ctx":\([0-9]*\).*/  n_ctx: \1/p' /tmp/local-llm-props-${label}.json | head -1
  fi
}

echo "== Containers =="
docker compose --project-directory "$ROOT" ps 2>&1 || true
echo

probe "exec" "$EXEC_BASE"
echo
probe "smart" "$SMART_BASE"
echo

echo "== GPU =="
nvidia-smi --query-gpu=index,name,temperature.gpu,power.draw,power.limit,utilization.gpu,utilization.memory,memory.used,memory.total --format=csv 2>&1 || echo "nvidia-smi failed"
echo

echo "== Recent Exec Logs =="
docker logs --tail 12 qwen35-4b-exec 2>&1 || true
echo
echo "== Recent Smart Logs =="
docker logs --tail 12 qwen35-9b-smart 2>&1 || echo "(smart not running)"
