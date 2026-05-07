#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

BASE_URL="http://${LLM_BIND_HOST:-127.0.0.1}:${LLM_PORT:-8000}"

echo "== Local LLM Status =="
echo "Endpoint: ${BASE_URL}/v1"
echo "Model: ${SERVED_MODEL_NAME:-unknown} (${MODEL_ID:-unknown})"
echo

echo "== Container =="
docker compose --project-directory "$ROOT" ps
echo

echo "== Health =="
if curl -fsS --max-time 3 "${BASE_URL}/health" >/dev/null; then
  echo "health: ok"
else
  echo "health: failed"
fi

if curl -fsS --max-time 5 "${BASE_URL}/v1/models" >/tmp/local-llm-models.json; then
  jq -r '.data[]?.id' /tmp/local-llm-models.json 2>/dev/null | sed 's/^/loaded model: /' || cat /tmp/local-llm-models.json
else
  echo "models: unavailable"
fi
echo

echo "== Recent Throughput =="
metric_value() {
  awk -v metric="$1" '$1 ~ "^" metric "\\{" {print $2; exit}' "$2"
}

if curl -fsS --max-time 5 "${BASE_URL}/metrics" >/tmp/local-llm-metrics-a.txt; then
  sleep 2
  if curl -fsS --max-time 5 "${BASE_URL}/metrics" >/tmp/local-llm-metrics-b.txt; then
    prompt_a="$(metric_value 'vllm:prompt_tokens_total' /tmp/local-llm-metrics-a.txt)"
    prompt_b="$(metric_value 'vllm:prompt_tokens_total' /tmp/local-llm-metrics-b.txt)"
    gen_a="$(metric_value 'vllm:generation_tokens_total' /tmp/local-llm-metrics-a.txt)"
    gen_b="$(metric_value 'vllm:generation_tokens_total' /tmp/local-llm-metrics-b.txt)"
    running="$(metric_value 'vllm:num_requests_running' /tmp/local-llm-metrics-b.txt)"
    waiting="$(metric_value 'vllm:num_requests_waiting' /tmp/local-llm-metrics-b.txt)"
    awk -v pa="${prompt_a:-0}" -v pb="${prompt_b:-0}" -v ga="${gen_a:-0}" -v gb="${gen_b:-0}" -v r="${running:-0}" -v w="${waiting:-0}" \
      'BEGIN { printf "prompt tok/s: %.2f\noutput tok/s: %.2f\nrunning: %.0f\nwaiting: %.0f\n", (pb-pa)/2, (gb-ga)/2, r, w }'
  else
    echo "metrics: unavailable on second sample"
  fi
else
  echo "metrics: unavailable"
fi
echo

echo "== GPU =="
nvidia-smi --query-gpu=index,name,temperature.gpu,power.draw,power.limit,utilization.gpu,utilization.memory,memory.used,memory.total,pcie.link.gen.current,pcie.link.width.current --format=csv
echo

echo "== Recent Logs =="
docker logs --tail 30 local-llm-vllm 2>&1 || true
