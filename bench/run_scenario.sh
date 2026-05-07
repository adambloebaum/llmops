#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/.env"

if [[ $# -ne 4 ]]; then
  echo "usage: $0 <scenario_name> <input_tokens> <output_tokens> <prompts_per_concurrency>" >&2
  exit 2
fi

scenario="$1"
input_tokens="$2"
output_tokens="$3"
prompts_per_concurrency="$4"

mkdir -p "$ROOT/bench/artifacts"

for concurrency in 1 4 8 16; do
  docker exec local-llm-vllm vllm bench serve \
    --backend openai-chat \
    --base-url "http://127.0.0.1:8000" \
    --endpoint /v1/chat/completions \
    --model "$SERVED_MODEL_NAME" \
    --tokenizer "$MODEL_ID" \
    --dataset-name random \
    --random-input-len "$input_tokens" \
    --random-output-len "$output_tokens" \
    --num-prompts $((concurrency * prompts_per_concurrency)) \
    --request-rate inf \
    --max-concurrency "$concurrency" \
    --temperature 0 \
    --save-result \
    --result-filename "/models/bench_${scenario}_c${concurrency}.json" \
    2>&1 | tee "$ROOT/bench/artifacts/${scenario}_c${concurrency}.log"
done
